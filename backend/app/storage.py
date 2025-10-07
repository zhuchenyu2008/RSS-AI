from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional, Tuple

from .models import ArticleCreate, ArticleInDB, ReportCreate, ReportInDB


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
                matched_keywords TEXT,
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
        try:
            conn.execute(
                "ALTER TABLE articles ADD COLUMN matched_keywords TEXT"
            )
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                timeframe_start TEXT NOT NULL,
                timeframe_end TEXT NOT NULL,
                article_count INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(report_type, timeframe_start, timeframe_end)
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC);
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
                INSERT INTO articles (feed_url, item_uid, title, link, pub_date, author, summary_text, matched_keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.feed_url,
                    article.item_uid,
                    article.title,
                    article.link,
                    article.pub_date,
                    article.author,
                    article.summary_text,
                    json.dumps(article.matched_keywords, ensure_ascii=False) if article.matched_keywords else "[]",
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
        items = [_row_to_article(r) for r in rows]
        return total, items


def get_article(article_id: int) -> Optional[ArticleInDB]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return _row_to_article(row) if row else None


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


def list_articles_in_range(start: datetime, end: datetime) -> List[ArticleInDB]:
    start_str = start.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end.strftime("%Y-%m-%d %H:%M:%S")
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM articles
            WHERE created_at >= ? AND created_at < ?
            ORDER BY created_at ASC
            """,
            (start_str, end_str),
        ).fetchall()
        return [_row_to_article(r) for r in rows]


def _row_to_article(row: sqlite3.Row) -> ArticleInDB:
    if row is None:
        raise ValueError("row is None")
    data = dict(row)
    raw_keywords = data.get("matched_keywords")
    if isinstance(raw_keywords, str):
        try:
            parsed = json.loads(raw_keywords)
            if isinstance(parsed, list):
                data["matched_keywords"] = [str(k) for k in parsed if isinstance(k, str)]
            else:
                data["matched_keywords"] = []
        except json.JSONDecodeError:
            data["matched_keywords"] = []
    elif raw_keywords is None:
        data["matched_keywords"] = []
    return ArticleInDB(**data)


def insert_report(report: ReportCreate) -> Optional[int]:
    with _connect() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO reports (report_type, title, summary_text, timeframe_start, timeframe_end, article_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_type,
                    report.title,
                    report.summary_text,
                    report.timeframe_start,
                    report.timeframe_end,
                    report.article_count,
                ),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            conn.execute(
                """
                UPDATE reports
                SET title = ?, summary_text = ?, article_count = ?, created_at = datetime('now')
                WHERE report_type = ? AND timeframe_start = ? AND timeframe_end = ?
                """,
                (
                    report.title,
                    report.summary_text,
                    report.article_count,
                    report.report_type,
                    report.timeframe_start,
                    report.timeframe_end,
                ),
            )
            row = conn.execute(
                "SELECT id FROM reports WHERE report_type = ? AND timeframe_start = ? AND timeframe_end = ?",
                (
                    report.report_type,
                    report.timeframe_start,
                    report.timeframe_end,
                ),
            ).fetchone()
            return int(row[0]) if row else None


def list_reports(limit: int = 20, offset: int = 0, report_type: Optional[str] = None) -> Tuple[int, List[ReportInDB]]:
    with _connect() as conn:
        params: List[object] = []
        where = ""
        if report_type:
            where = " WHERE report_type = ?"
            params.append(report_type)
        total_row = conn.execute(f"SELECT COUNT(*) as c FROM reports{where}", params).fetchone()
        total = int(total_row[0]) if total_row else 0

        params2 = list(params)
        params2.extend([limit, offset])
        rows = conn.execute(
            f"SELECT * FROM reports{where} ORDER BY timeframe_end DESC LIMIT ? OFFSET ?",
            params2,
        ).fetchall()
        items = [ReportInDB(**dict(r)) for r in rows]
        return total, items


def get_report(report_id: int) -> Optional[ReportInDB]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        return ReportInDB(**dict(row)) if row else None
