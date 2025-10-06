from __future__ import annotations

import hashlib
from typing import Dict, List, Optional
import feedparser


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


def fetch_feed(feed_url: str) -> List[RSSItem]:
    parsed = feedparser.parse(feed_url)
    items: List[RSSItem] = []
    for entry in parsed.entries:
        try:
            items.append(RSSItem(feed_url, entry))
        except Exception:
            # skip malformed entries
            continue
    return items

