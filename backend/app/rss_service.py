from __future__ import annotations

import hashlib
import logging
from typing import List, Optional
import time
import calendar

import feedparser
import httpx


class RSSItem:
    def __init__(self, feed_url: str, entry: dict):
        self.feed_url = feed_url
        self.title: str = entry.get("title", "").strip()
        self.link: str = entry.get("link", "").strip()
        # Try several fields for date
        self.pub_date: Optional[str] = (
            entry.get("published")
            or entry.get("pubDate")
            or entry.get("updated")
            or None
        )
        # author may be in 'author' or dc:creator
        self.author: Optional[str] = entry.get("author") or entry.get("dc_creator") or None
        # content
        content = ""
        if entry.get("content") and isinstance(entry["content"], list) and entry["content"]:
            content = entry["content"][0].get("value", "")
        elif entry.get("summary"):
            content = entry.get("summary", "")
        self.content: str = content

        # Unique key: prefer guid/id; else hash of link+title
        uid = entry.get("id") or entry.get("guid") or None
        if not uid:
            base = f"{self.link}|{self.title}".encode("utf-8", errors="ignore")
            uid = hashlib.sha1(base).hexdigest()
        self.uid: str = str(uid)

        # For sorting by recency
        st = entry.get("published_parsed") or entry.get("updated_parsed") or None
        ts = 0
        try:
            if st:
                ts = int(calendar.timegm(st))
        except Exception:
            try:
                # Fallback: try parse via feedparser' parsed value maybe struct_time like
                ts = int(time.time())
            except Exception:
                ts = 0
        self.sort_ts: int = ts


def fetch_feed(feed_url: str) -> List[RSSItem]:
    """Fetch RSS/Atom feed with httpx first (for better diagnostics),
    then parse with feedparser. Fallback to feedparser direct on failure.
    """
    content: Optional[bytes] = None
    try:
        headers = {
            "User-Agent": "RSS-AI/1.0 (+https://github.com/)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(feed_url, headers=headers)
            resp.raise_for_status()
            content = resp.content
            logging.debug(f"获取RSS成功 {feed_url} status={resp.status_code} bytes={len(content)}")
    except Exception as e:
        logging.warning(f"HTTP获取RSS失败，将直接解析URL: {feed_url} err={e}")

    try:
        parsed = feedparser.parse(content if content is not None else feed_url)
        if getattr(parsed, "bozo", 0):
            be = getattr(parsed, "bozo_exception", None)
            logging.debug(f"解析RSS存在异常 bozo={bool(parsed.bozo)} exc={be}")
        entries = getattr(parsed, "entries", []) or []
    except Exception as e:
        logging.exception(f"解析RSS失败: {feed_url} err={e}")
        entries = []

    items: List[RSSItem] = []
    for entry in entries:
        try:
            items.append(RSSItem(feed_url, entry))
        except Exception as ex:
            logging.debug(f"跳过异常条目: {ex}")
            continue
    logging.info(f"RSS结果 {feed_url}: 共 {len(items)} 条")
    return items
