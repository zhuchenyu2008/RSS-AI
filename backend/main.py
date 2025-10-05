"""
RSS AI Backend
===============

这是后端服务的主程序，基于 FastAPI 编写并运行在端口 3601 上。功能包括：

1. 按照配置文件（`config.json`）中指定的 RSS 源定时获取最新文章。
2. 使用用户配置的 AI 模型（如 OpenAI）对文章内容进行中文总结，并排版输出。
3. 将总结后的内容推送到用户设置的 Telegram 机器人群组。
4. 提供 REST API 接口供前端获取、修改配置以及查看历史总结数据。

使用说明请参考根目录下的 README.md。
"""

import os
import json
import asyncio
import logging
from typing import List
from datetime import datetime

import xml.etree.ElementTree as ET
import aiohttp
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import sqlite3

# 定义文件路径
BASE_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DB_FILE = os.path.join(BASE_DIR, "rss.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "rssai.log")

# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)

# 配置日志
logger = logging.getLogger("rssai")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# 创建 FastAPI 实例并配置跨域
app = FastAPI(title="RSS AI Summarizer API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_config() -> dict:
    """加载配置文件。若文件不存在则生成默认配置。"""
    if not os.path.exists(CONFIG_FILE):
        default = {
            "rss_urls": [],
            "openai": {
                "api_key": "",
                # OpenAI 通用接口地址，可在配置中指定其他兼容接口
                "api_base": "https://api.openai.com/v1/chat/completions",
                # 默认模型
                "model": "gpt-3.5-turbo"
            },
            "telegram": {
                # Telegram 机器人 token
                "token": "",
                # 发送消息的群组或频道 ID
                "chat_id": ""
            },
            # 获取 RSS 的时间间隔（秒）
            "fetch_interval": 3600
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    """保存配置文件。"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# 初始化数据库
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guid TEXT UNIQUE,
        title TEXT,
        link TEXT,
        published TEXT,
        author TEXT,
        summary TEXT,
        created_at TEXT
    );
    """
)
conn.commit()


async def summarize_content(content: str, config: dict) -> str:
    """
    使用用户配置的 AI 接口对内容进行总结。

    :param content: 原始文章内容或摘要
    :param config: 配置字典，包含 openai 信息
    :return: AI 返回的总结文本
    """
    # 若未配置 API Key 或模型，则直接返回空
    if not config.get("openai") or not config["openai"].get("api_key"):
        logger.error("OpenAI API key 未配置，无法总结文章。")
        return ""

    api_key = config["openai"]["api_key"]
    api_base = config["openai"].get("api_base", "https://api.openai.com/v1/chat/completions")
    model = config["openai"].get("model", "gpt-3.5-turbo")

    # 构建提示词，要求中文总结
    prompt = (
        "请对以下RSS文章内容进行总结，使用中文，并突出关键信息:\n"
        "内容:\n"
        f"{content}\n\n"
        "请用简短的段落概述该内容。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一名中文内容撰写助手，擅长提炼文章关键内容并用简洁的语言总结。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 500
    }
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_base, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"AI API 请求失败，状态码 {resp.status}，响应内容: {text}")
                    return ""
                data = await resp.json()
                # 兼容不同接口结构，选择第一个回答
                try:
                    summary = data["choices"][0]["message"]["content"].strip()
                except Exception:
                    summary = data.get("summary", "").strip() if isinstance(data, dict) else ""
                return summary
    except Exception as e:
        logger.exception(f"调用 AI 接口时出错: {e}")
        return ""


async def send_to_telegram(message: str, config: dict) -> None:
    """
    向 Telegram 群组发送消息。

    :param message: 需要发送的消息，支持 HTML 格式
    :param config: 配置字典，包含 telegram token 和 chat_id
    """
    telegram_cfg = config.get("telegram", {})
    token = telegram_cfg.get("token")
    chat_id = telegram_cfg.get("chat_id")
    if not token or not chat_id:
        # 未配置 Telegram，则记录警告并退出
        logger.warning("Telegram token 或 chat_id 未配置，跳过发送 Telegram 消息。")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as resp:
                if resp.status != 200:
                    logger.error(f"发送 Telegram 消息失败，状态码 {resp.status}")
                else:
                    logger.info("已向 Telegram 发送消息。")
    except Exception as e:
        logger.exception(f"发送 Telegram 消息时出错: {e}")


async def fetch_and_parse(session: aiohttp.ClientSession, rss_url: str) -> List[dict]:
    """
    从 RSS 或 Atom 源获取并解析文章。

    :param session: aiohttp 会话
    :param rss_url: RSS/Atom 地址
    :return: 列表，其中每个元素包含文章的基本字段
    """
    items: List[dict] = []
    try:
        async with session.get(rss_url) as resp:
            if resp.status != 200:
                logger.error(f"无法获取 RSS 源 {rss_url}，HTTP 状态 {resp.status}")
                return items
            text = await resp.text()
    except Exception as e:
        logger.exception(f"请求 RSS 源 {rss_url} 时出错: {e}")
        return items
    try:
        root = ET.fromstring(text)
    except Exception as e:
        logger.exception(f"解析 RSS XML 时出错: {e}")
        return items
    # 解析 RSS (item)
    for item in root.findall('.//item'):
        guid = item.findtext('guid') or item.findtext('id') or item.findtext('link') or ''
        title = item.findtext('title') or ''
        link = item.findtext('link') or ''
        pub_date = item.findtext('pubDate') or item.findtext('{http://purl.org/dc/elements/1.1/}date') or ''
        author = item.findtext('author') or item.findtext('{http://purl.org/dc/elements/1.1/}creator') or ''
        description = item.findtext('description') or ''
        items.append({
            'guid': guid.strip(),
            'title': title.strip(),
            'link': link.strip(),
            'published': pub_date.strip(),
            'author': author.strip(),
            'content': description.strip(),
        })
    # 解析 Atom (entry)
    ns = {'atom': 'http://www.w3.org/2005/Atom', 'dc': 'http://purl.org/dc/elements/1.1/'}
    for entry in root.findall('.//atom:entry', ns):
        guid = entry.findtext('atom:id', default='', namespaces=ns) or entry.findtext('atom:link', default='', namespaces=ns)
        title = entry.findtext('atom:title', default='', namespaces=ns)
        link_el = entry.find('atom:link', ns)
        link = ''
        if link_el is not None:
            link = link_el.attrib.get('href', '')
        pub_date = entry.findtext('atom:published', default='', namespaces=ns) or entry.findtext('atom:updated', default='', namespaces=ns)
        author_el = entry.find('atom:author/atom:name', ns)
        author = author_el.text if author_el is not None else ''
        # 有些 Atom 使用 dc:creator
        if not author:
            author = entry.findtext('dc:creator', default='', namespaces=ns)
        summary_el = entry.find('atom:summary', ns) or entry.find('atom:content', ns)
        description = summary_el.text if summary_el is not None else ''
        items.append({
            'guid': guid.strip(),
            'title': title.strip(),
            'link': link.strip(),
            'published': pub_date.strip(),
            'author': author.strip(),
            'content': description.strip(),
        })
    return items


async def process_feed(config: dict) -> None:
    """
    遍历配置中的 RSS 源，抓取并处理最新文章。

    :param config: 当前配置
    """
    rss_urls: List[str] = config.get("rss_urls", [])
    logger.info(f"开始处理 {len(rss_urls)} 个 RSS 源")
    async with aiohttp.ClientSession() as session:
        for rss_url in rss_urls:
            articles = await fetch_and_parse(session, rss_url)
            for entry in articles:
                guid = entry['guid'] or entry['link']
                if not guid:
                    continue
                # 检查数据库中是否已存在
                existing = cur.execute("SELECT 1 FROM articles WHERE guid = ?", (guid,)).fetchone()
                if existing:
                    continue
                title = entry['title']
                link = entry['link']
                published = entry['published']
                author = entry['author']
                summary_content = entry['content']
                # 调用 AI 总结内容
                logger.info(f"正在总结文章: {title}")
                summary = await summarize_content(summary_content, config)
                # 组装消息内容
                message = (
                    f"<b>标题:</b> {title}\n"
                    f"<b>链接:</b> {link}\n"
                    f"<b>发布时间:</b> {published}\n"
                    f"<b>作者:</b> {author}\n\n"
                    f"{summary}"
                )
                # 推送到 Telegram
                if summary:
                    await send_to_telegram(message, config)
                # 写入数据库
                cur.execute(
                    "INSERT OR IGNORE INTO articles (guid, title, link, published, author, summary, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (guid, title, link, published, author, summary, datetime.utcnow().isoformat())
                )
                conn.commit()
                logger.info(f"已保存文章 {title}")


async def schedule_worker() -> None:
    """后台定时任务，按配置的间隔定时抓取 RSS 并总结。"""
    while True:
        config = load_config()
        interval = max(int(config.get("fetch_interval", 3600)), 60)
        try:
            await process_feed(config)
        except Exception as e:
            logger.exception(f"后台任务出现错误: {e}")
        # 按照配置的间隔等待
        await asyncio.sleep(interval)


@app.on_event("startup")
async def startup_event() -> None:
    """FastAPI 启动事件，创建后台任务。"""
    asyncio.create_task(schedule_worker())


@app.get("/api/config")
async def api_get_config() -> dict:
    """获取当前配置。"""
    return load_config()


@app.post("/api/config")
async def api_update_config(cfg: dict, background_tasks: BackgroundTasks) -> dict:
    """更新配置，并立即触发一次抓取。"""
    save_config(cfg)
    logger.info("配置已更新。")
    # 立即执行一次抓取任务，避免等待下一个间隔
    background_tasks.add_task(process_feed, cfg)
    return {"status": "ok"}


@app.get("/api/summaries")
async def api_get_summaries(limit: int = 20) -> List[dict]:
    """获取最近的总结记录。"""
    limit = max(1, min(limit, 100))
    rows = cur.execute(
        "SELECT title, link, published, author, summary FROM articles ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    result: List[dict] = []
    for row in rows:
        result.append({
            "title": row["title"],
            "link": row["link"],
            "published": row["published"],
            "author": row["author"],
            "summary": row["summary"],
        })
    return result


@app.get("/api/run")
async def api_run(background_tasks: BackgroundTasks) -> dict:
    """手动触发一次抓取和总结任务。"""
    cfg = load_config()
    background_tasks.add_task(process_feed, cfg)
    return {"status": "started"}
