from __future__ import annotations

import logging
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import load_settings, save_settings
from .models import (
    AppSettings,
    ArticleInDB,
    ArticleListResponse,
    FetchRequest,
    FetchResponse,
    HealthResponse,
)
from .storage import init_db, list_articles, get_article, insert_article, prune_articles, exists_article
from .rss_service import fetch_feed
from .extractor import extract_from_url
from .ai_client import AIClient, fallback_summary
from .telegram_client import TelegramClient
from .scheduler import FetchScheduler


app = FastAPI(title="RSS-AI API", version="0.1.0")

# CORS for separated frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_scheduler: Optional[FetchScheduler] = None


def _setup_logging():
    settings = load_settings()
    level = getattr(logging, settings.logging.level.upper(), logging.INFO)
    os.makedirs(os.path.dirname(settings.logging.file), exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt)
    # Add file handler
    fh = logging.FileHandler(settings.logging.file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(fh)


def _build_ai_client(settings: AppSettings) -> Optional[AIClient]:
    if settings.ai.enabled and settings.ai.api_key:
        return AIClient(
            base_url=settings.ai.base_url,
            api_key=settings.ai.api_key,
            model=settings.ai.model,
            temperature=settings.ai.temperature,
        )
    return None


def _build_telegram_client(settings: AppSettings) -> Optional[TelegramClient]:
    if settings.telegram.enabled and settings.telegram.bot_token and settings.telegram.chat_id:
        return TelegramClient(bot_token=settings.telegram.bot_token)
    return None


def _format_telegram_message(item: dict) -> str:
    # item has title, link, pubDate, author, summary_text
    title = item.get("title", "")
    link = item.get("link", "")
    pub_date = item.get("pubDate", "")
    author = item.get("author", "")
    summary_text = item.get("summary_text", "")
    # HTML formatting for Telegram
    parts = [
        f"<b>{title}</b>",
        f"<a href=\"{link}\">原文链接</a>",
    ]
    meta = []
    if pub_date:
        meta.append(f"发布时间：{pub_date}")
    if author:
        meta.append(f"作者：{author}")
    if meta:
        parts.append(" | ".join(meta))
    if summary_text:
        parts.append("\n" + summary_text)
    return "\n".join(parts)


def do_fetch_once(force: bool = False) -> FetchResponse:
    settings = load_settings()
    ai = _build_ai_client(settings)
    tg = _build_telegram_client(settings)

    new_items = 0
    processed = 0
    feeds_count = len(settings.fetch.feeds)
    for feed in settings.fetch.feeds:
        logging.info(f"开始抓取: {feed}")
        try:
            entries = fetch_feed(feed)
        except Exception as e:
            logging.exception(f"抓取失败 {feed}: {e}")
            continue
        logging.info(f"抓取完成: {feed}，条目数 {len(entries)}")
        # 按时间倒序优先处理，并限制单源抓取上限
        if entries:
            try:
                entries.sort(key=lambda x: getattr(x, 'sort_ts', 0), reverse=True)
            except Exception:
                pass
            limit = max(1, int(settings.fetch.per_feed_limit))
            if len(entries) > limit:
                logging.info(f"限制单源抓取上限为 {limit} 条（优先最新）")
                entries = entries[:limit]
        dup = 0
        for e in entries:
            processed += 1
            if not force and exists_article(feed, e.uid):
                dup += 1
                continue

            # summarize via AI or fallback
            ai_obj = None
            if ai is not None:
                logging.debug(f"AI总结开始: {e.title}")
                # Prefer extracted fulltext from original page when enabled
                content_for_ai = None
                if settings.fetch.use_article_page and e.link:
                    content_for_ai = extract_from_url(e.link, timeout=float(settings.fetch.article_timeout_seconds))
                    if content_for_ai:
                        logging.info("使用原文抽取正文进行AI总结")
                if not content_for_ai:
                    content_for_ai = e.content
                ai_obj = ai.summarize(
                    title=e.title,
                    link=e.link,
                    pub_date=e.pub_date,
                    author=e.author,
                    content=content_for_ai,
                    system_prompt=settings.ai.system_prompt,
                    user_prompt_template=settings.ai.user_prompt_template,
                )
            if ai_obj is None:
                logging.info("AI未启用或调用失败，使用降级摘要")
                content_for_fallback = None
                if settings.fetch.use_article_page and e.link:
                    content_for_fallback = extract_from_url(e.link, timeout=float(settings.fetch.article_timeout_seconds))
                ai_obj = fallback_summary(
                    e.title,
                    e.link,
                    e.pub_date,
                    e.author,
                    content_for_fallback or e.content,
                )

            from .models import ArticleCreate  # local import to avoid circular

            article = ArticleCreate(
                feed_url=feed,
                item_uid=e.uid,
                title=ai_obj.get("title") or e.title,
                link=e.link,
                pub_date=ai_obj.get("pubDate") or e.pub_date,
                author=ai_obj.get("author") or e.author,
                summary_text=ai_obj.get("summary_text") or "",
            )
            row_id = insert_article(article)
            if row_id:
                new_items += 1
                logging.info(f"新文章入库: {article.title} ({row_id})")
                prune_articles(settings.fetch.max_items)
                # send to telegram
                if tg is not None:
                    text = _format_telegram_message(ai_obj)
                    ok = tg.send_message(settings.telegram.chat_id, text, parse_mode="HTML", disable_web_page_preview=False)
                    logging.info(f"推送Telegram: {'成功' if ok else '失败'}")
            else:
                logging.debug(f"入库跳过或失败(可能重复): {article.title}")
        logging.info(f"汇总 {feed}: 新增 {new_items}，重复 {dup}，本次处理 {len(entries)} 条")
    return FetchResponse(
        fetched_feeds=feeds_count,
        new_items=new_items,
        processed_items=processed,
        message="完成",
    )


@app.on_event("startup")
def on_startup():
    _setup_logging()
    settings = load_settings()
    logging.info("应用启动中…")
    init_db()
    global _scheduler
    _scheduler = FetchScheduler(settings.fetch.interval_minutes, task=lambda: do_fetch_once(force=False))
    _scheduler.start()
    logging.info("应用已启动")


@app.on_event("shutdown")
def on_shutdown():
    logging.info("应用即将停止…")
    global _scheduler
    if _scheduler:
        _scheduler.stop()
    logging.info("应用已停止")


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@app.get("/api/settings", response_model=AppSettings)
def get_settings():
    s = load_settings()
    # 不回显敏感信息为空
    safe = s.model_copy(deep=True)
    if safe.ai.api_key:
        safe.ai.api_key = "***"
    if safe.telegram.bot_token:
        safe.telegram.bot_token = "***"
    # 为避免用户从零填写提示词，若为空则回填默认提示词
    defaults = AppSettings()
    if not (safe.ai.system_prompt and safe.ai.system_prompt.strip()):
        safe.ai.system_prompt = defaults.ai.system_prompt
    if not (safe.ai.user_prompt_template and safe.ai.user_prompt_template.strip()):
        safe.ai.user_prompt_template = defaults.ai.user_prompt_template
    return safe


@app.put("/api/settings", response_model=AppSettings)
def update_settings(new_settings: AppSettings):
    # 注意：允许前端传入完整设置；若前端传***，不覆盖旧密钥
    old = load_settings()
    if new_settings.ai.api_key == "***":
        new_settings.ai.api_key = old.ai.api_key
    if new_settings.telegram.bot_token == "***":
        new_settings.telegram.bot_token = old.telegram.bot_token
    # 若提示词为空，填充为默认值，避免出现空白
    defaults = AppSettings()
    if not (new_settings.ai.system_prompt and new_settings.ai.system_prompt.strip()):
        new_settings.ai.system_prompt = defaults.ai.system_prompt
    if not (new_settings.ai.user_prompt_template and new_settings.ai.user_prompt_template.strip()):
        new_settings.ai.user_prompt_template = defaults.ai.user_prompt_template
    save_settings(new_settings)
    logging.info("配置已更新")
    # 重启调度器
    global _scheduler
    if _scheduler:
        _scheduler.update_interval(new_settings.fetch.interval_minutes)
    return get_settings()


@app.post("/api/fetch", response_model=FetchResponse)
def fetch_now(req: FetchRequest):
    logging.info("手动触发抓取…")
    result = do_fetch_once(force=req.force)
    return result


@app.get("/api/articles", response_model=ArticleListResponse)
def api_list_articles(limit: int = 20, offset: int = 0, feed: Optional[str] = None):
    total, items = list_articles(limit=limit, offset=offset, feed_url=feed)
    return ArticleListResponse(total=total, items=items)


@app.get("/api/articles/{article_id}", response_model=ArticleInDB)
def api_get_article(article_id: int):
    item = get_article(article_id)
    if not item:
        raise HTTPException(status_code=404, detail="Article not found")
    return item


def run():
    settings = load_settings()
    uvicorn.run("app.main:app", host=settings.server.host, port=settings.server.port, reload=False)


if __name__ == "__main__":
    run()
