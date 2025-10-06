from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import List, Optional, Tuple

from .models import ArticleCreate, ArticleInDB


DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "db.sqlite"))
_lock = threading.RLock()


def init_db():
    db_dir = os.path.dirname(DB_PATH)
    os.makedirs(db_dir, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_url TEXT NOT NULL,
                item_uid TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                pub_date TEXT,
                author TEXT,
                summary_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(feed_url, item_uid)
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at DESC);
            """
        )


@contextmanager
def _connect():
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        finally:
            conn.close()


def insert_article(article: ArticleCreate) -> Optional[int]:
    with _connect() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO articles (feed_url, item_uid, title, link, pub_date, author, summary_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.feed_url,
                    article.item_uid,
                    article.title,
                    article.link,
                    article.pub_date,
                    article.author,
                    article.summary_text,
                ),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def exists_article(feed_url: str, item_uid: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM articles WHERE feed_url = ? AND item_uid = ? LIMIT 1",
            (feed_url, item_uid),
        ).fetchone()
        return row is not None


def list_articles(limit: int = 20, offset: int = 0, feed_url: Optional[str] = None) -> Tuple[int, List[ArticleInDB]]:
    with _connect() as conn:
        params = []
        where = ""
        if feed_url:
            where = " WHERE feed_url = ?"
            params.append(feed_url)

        total_row = conn.execute(f"SELECT COUNT(*) as c FROM articles{where}", params).fetchone()
        total = int(total_row[0]) if total_row else 0

        params2 = list(params)
        params2.extend([limit, offset])
        rows = conn.execute(
            f"SELECT * FROM articles{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params2,
        ).fetchall()
        items = [ArticleInDB(**dict(r)) for r in rows]
        return total, items


def get_article(article_id: int) -> Optional[ArticleInDB]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return ArticleInDB(**dict(row)) if row else None


def prune_articles(max_items: int):
    if max_items <= 0:
        return
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM articles").fetchone()
        total = int(row[0]) if row else 0
        if total > max_items:
            # delete oldest beyond the newest max_items
            to_delete = total - max_items
            conn.execute(
                "DELETE FROM articles WHERE id IN (SELECT id FROM articles ORDER BY id ASC LIMIT ?)",
                (to_delete,),
            )
