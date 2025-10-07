from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

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
    ReportInDB,
    ReportListResponse,
    ReportGenerateRequest,
)
from .storage import (
    init_db,
    list_articles,
    get_article,
    insert_article,
    prune_articles,
    exists_article,
    list_reports,
    get_report,
)
from .rss_service import fetch_feed
from .extractor import extract_from_url
from .ai_client import AIClient, fallback_summary
from .telegram_client import TelegramClient
from .scheduler import FetchScheduler, AlignedScheduler
from .report_service import generate_report as run_report, BEIJING_TZ


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
_report_schedulers: Dict[str, AlignedScheduler] = {}


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


def _next_top_of_hour(now: datetime) -> datetime:
    local = now.astimezone(BEIJING_TZ)
    aligned = local.replace(minute=0, second=0, microsecond=0)
    if local >= aligned:
        aligned += timedelta(hours=1)
    return aligned.astimezone(timezone.utc)


def _next_midnight(now: datetime) -> datetime:
    local = now.astimezone(BEIJING_TZ)
    aligned = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if local >= aligned:
        aligned += timedelta(days=1)
    return aligned.astimezone(timezone.utc)


def _run_report(report_type: str):
    settings = load_settings()
    if report_type == "daily" and not settings.reports.daily_enabled:
        logging.debug("日报已禁用，跳过生成")
        return
    if report_type == "hourly" and not settings.reports.hourly_enabled:
        logging.debug("小时报已禁用，跳过生成")
        return
    ai = _build_ai_client(settings)
    tg = _build_telegram_client(settings)
    run_report(report_type, settings=settings, ai_client=ai, telegram_client=tg)


def _configure_report_schedulers(settings: AppSettings):
    global _report_schedulers

    def ensure_scheduler(report_type: str, enabled: bool, compute):
        scheduler = _report_schedulers.get(report_type)
        if enabled:
            if scheduler is None:
                scheduler = AlignedScheduler(
                    name=f"ReportScheduler-{report_type}",
                    compute_next_run=compute,
                    task=lambda rt=report_type: _run_report(rt),
                )
                _report_schedulers[report_type] = scheduler
                # Generate once immediately for当前时间段
                _run_report(report_type)
            scheduler.start()
        else:
            if scheduler is not None:
                scheduler.stop()
                del _report_schedulers[report_type]

    ensure_scheduler("hourly", settings.reports.hourly_enabled, _next_top_of_hour)
    ensure_scheduler("daily", settings.reports.daily_enabled, _next_midnight)


def _manual_report_timeframe(report_type: str) -> Tuple[datetime, datetime]:
    now_local = datetime.now(BEIJING_TZ)
    if report_type == "daily":
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = now_local
    elif report_type == "hourly":
        end_local = now_local
        start_local = end_local - timedelta(hours=1)
    else:
        raise ValueError("unsupported report type")
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc


def _format_telegram_message(item: dict, matched_keywords: Optional[list[str]] = None) -> str:
    # item has title, link, pubDate, author, summary_text
    title = item.get("title", "")
    link = item.get("link", "")
    pub_date = item.get("pubDate", "")
    author = item.get("author", "")
    summary_text = item.get("summary_text", "")
    keywords = matched_keywords or []
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
    if keywords:
        meta.append("关键词：" + "、".join(keywords))
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
    duplicates = 0
    failed_items = 0
    ai_calls = 0
    ai_success = 0
    ai_failed = 0
    tokens_prompt = 0
    tokens_completion = 0
    tokens_total = 0
    feed_fetch_failed = 0
    raw_keywords = getattr(settings.fetch, "filter_keywords", []) or []
    filter_keywords = [kw.strip() for kw in raw_keywords if isinstance(kw, str) and kw.strip()]
    keyword_terms = list(filter_keywords)
    keyword_match_hits = 0
    keyword_match_articles = 0
    for feed in settings.fetch.feeds:
        logging.info(f"开始抓取: {feed}")
        try:
            entries = fetch_feed(feed)
        except Exception as e:
            logging.exception(f"抓取失败 {feed}: {e}")
            feed_fetch_failed += 1
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

            # Prefer extracted fulltext for downstream usage
            extracted_content = None
            if settings.fetch.use_article_page and e.link:
                extracted_content = extract_from_url(
                    e.link,
                    timeout=float(settings.fetch.article_timeout_seconds),
                )
                if extracted_content:
                    logging.info("使用原文抽取正文进行内容处理")

            content_source = extracted_content or e.content or ""
            haystack_parts = [e.title, e.author, e.content, extracted_content]
            haystack = " \n ".join(part for part in haystack_parts if part)
            matched_keywords: list[str] = []
            if keyword_terms:
                matched_keywords = [kw for kw in keyword_terms if kw and kw in haystack]
                if matched_keywords:
                    matched_keywords = list(dict.fromkeys(matched_keywords))
                keywords_matched = bool(matched_keywords)
                if keywords_matched:
                    keyword_match_articles += 1
                    keyword_match_hits += len(matched_keywords)
            else:
                keywords_matched = True
            if not keywords_matched and filter_keywords:
                logging.debug("关键词未匹配，跳过AI总结与推送: %s", e.title)

            # summarize via AI when keywords matched; otherwise fallback
            ai_obj = None
            attempted_ai = False
            if ai is not None and keywords_matched:
                logging.debug(f"AI总结开始: {e.title}")
                attempted_ai = True
                ai_calls += 1
                ai_obj = ai.summarize(
                    title=e.title,
                    link=e.link,
                    pub_date=e.pub_date,
                    author=e.author,
                    content=content_source,
                    system_prompt=settings.ai.system_prompt,
                    user_prompt_template=settings.ai.user_prompt_template,
                )
                if ai_obj is None:
                    ai_failed += 1
            if ai_obj is None:
                if attempted_ai:
                    logging.info("AI调用失败，使用降级摘要")
                ai_obj = fallback_summary(
                    e.title,
                    e.link,
                    e.pub_date,
                    e.author,
                    content_source or e.content,
                )
            else:
                ai_success += 1
                usage = ai_obj.get("_ai_usage") if isinstance(ai_obj, dict) else None
                if isinstance(usage, dict):
                    tokens_prompt += int(usage.get("prompt_tokens", 0) or 0)
                    tokens_completion += int(usage.get("completion_tokens", 0) or 0)
                    tokens_total += int(usage.get("total_tokens", 0) or 0)

            from .models import ArticleCreate  # local import to avoid circular

            article = ArticleCreate(
                feed_url=feed,
                item_uid=e.uid,
                title=ai_obj.get("title") or e.title,
                link=e.link,
                pub_date=ai_obj.get("pubDate") or e.pub_date,
                author=ai_obj.get("author") or e.author,
                summary_text=ai_obj.get("summary_text") or "",
                matched_keywords=matched_keywords,
            )
            try:
                row_id = insert_article(article)
                if row_id:
                    new_items += 1
                    logging.info(f"新文章入库: {article.title} ({row_id})")
                    prune_articles(settings.fetch.max_items)
                    # send to telegram
                    if tg is not None and keywords_matched:
                        text = _format_telegram_message(ai_obj, matched_keywords)
                        ok = tg.send_message(settings.telegram.chat_id, text, parse_mode="HTML", disable_web_page_preview=False)
                        logging.info(f"推送Telegram: {'成功' if ok else '失败'}")
                else:
                    logging.debug(f"入库跳过或失败(可能重复): {article.title}")
            except Exception as ex:
                failed_items += 1
                logging.exception(f"入库过程中异常: {ex}")
        logging.info(f"汇总 {feed}: 新增 {new_items}，重复 {dup}，本次处理 {len(entries)} 条")
        duplicates += dup
    # 抓取汇总后报告到 Telegram（可选）
    if tg is not None and settings.telegram.push_summary:
        summary_lines = [
            "<b>RSS-AI 抓取汇总</b>",
            f"RSS 源：{feeds_count} 个",
            f"获取条目：{processed} 条",
            f"新增入库：{new_items} 条",
            f"重复跳过：{duplicates} 条",
            f"处理失败：{failed_items} 条",
        ]
        if ai is not None:
            summary_lines.extend([
                f"AI 调用：{ai_calls} 次（成功 {ai_success}，失败 {ai_failed}）",
                f"Token 消耗：prompt {tokens_prompt}，completion {tokens_completion}，total {tokens_total}",
            ])
        if filter_keywords:
            summary_lines.append(
                f"关键词匹配：{keyword_match_hits} 次，命中文章：{keyword_match_articles} 篇"
            )
        if feed_fetch_failed:
            summary_lines.append(f"源抓取失败：{feed_fetch_failed} 个源")
        tg.send_message(settings.telegram.chat_id, "\n".join(summary_lines), parse_mode="HTML", disable_web_page_preview=True)

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
    _configure_report_schedulers(settings)
    logging.info("应用已启动")


@app.on_event("shutdown")
def on_shutdown():
    logging.info("应用即将停止…")
    global _scheduler
    if _scheduler:
        _scheduler.stop()
    global _report_schedulers
    for sched in list(_report_schedulers.values()):
        sched.stop()
    _report_schedulers.clear()
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
    if not (safe.reports.system_prompt and safe.reports.system_prompt.strip()):
        safe.reports.system_prompt = defaults.reports.system_prompt
    if not (safe.reports.user_prompt_template and safe.reports.user_prompt_template.strip()):
        safe.reports.user_prompt_template = defaults.reports.user_prompt_template
    if not safe.reports.report_timeout_seconds:
        safe.reports.report_timeout_seconds = defaults.reports.report_timeout_seconds
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
    if not (new_settings.reports.system_prompt and new_settings.reports.system_prompt.strip()):
        new_settings.reports.system_prompt = defaults.reports.system_prompt
    if not (new_settings.reports.user_prompt_template and new_settings.reports.user_prompt_template.strip()):
        new_settings.reports.user_prompt_template = defaults.reports.user_prompt_template
    if not new_settings.reports.report_timeout_seconds:
        new_settings.reports.report_timeout_seconds = defaults.reports.report_timeout_seconds
    save_settings(new_settings)
    logging.info("配置已更新")
    # 重启调度器
    global _scheduler
    if _scheduler:
        _scheduler.update_interval(new_settings.fetch.interval_minutes)
    _configure_report_schedulers(new_settings)
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


@app.get("/api/reports", response_model=ReportListResponse)
def api_list_reports(limit: int = 10, offset: int = 0, report_type: Optional[str] = None):
    total, items = list_reports(limit=limit, offset=offset, report_type=report_type)
    return ReportListResponse(total=total, items=items)


@app.post("/api/reports/generate", response_model=ReportInDB)
def api_generate_report(req: ReportGenerateRequest):
    settings = load_settings()
    report_type = req.report_type
    start_utc, end_utc = _manual_report_timeframe(report_type)
    ai = _build_ai_client(settings)
    tg = _build_telegram_client(settings)
    report_id = run_report(
        report_type,
        settings=settings,
        ai_client=ai,
        telegram_client=tg,
        start_override=start_utc,
        end_override=end_utc,
    )
    if report_id is None:
        raise HTTPException(status_code=400, detail="报告生成失败或时间范围内无可用数据")
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def run():
    settings = load_settings()
    uvicorn.run("app.main:app", host=settings.server.host, port=settings.server.port, reload=False)


if __name__ == "__main__":
    run()
