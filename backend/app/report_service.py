from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Optional

from .ai_client import AIClient
from .models import AppSettings, ReportCreate, SettingsReports
from .storage import insert_report, list_articles_in_range
from .telegram_client import TelegramClient


UTC = timezone.utc
BEIJING_TZ = timezone(timedelta(hours=8))


def _floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _floor_to_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _format_range_local(start: datetime, end: datetime) -> str:
    start_local = start.astimezone(BEIJING_TZ)
    end_local = end.astimezone(BEIJING_TZ)
    return f"{start_local.strftime('%Y-%m-%d %H:%M')} - {end_local.strftime('%Y-%m-%d %H:%M')} 北京时间"


def _fallback_report_summary(
    *,
    label: str,
    timeframe_display: str,
    article_count: int,
    feed_counts: Counter,
    article_lines: list[str],
) -> str:
    lines = [
        f"{label}时间范围：{timeframe_display}",
        f"收录文章：{article_count} 篇",
    ]
    if feed_counts:
        feed_parts = [f"{feed}（{count}）" for feed, count in feed_counts.most_common(6)]
        lines.append("主要来源：" + "，".join(feed_parts))
    if article_lines:
        lines.append("")
        lines.append("重点文章：")
        lines.extend(article_lines[:5])
    else:
        lines.append("该时间段内没有新的文章。")
    return "\n".join(lines)


def _build_article_lines(articles: list, max_items: int) -> list[str]:
    lines: list[str] = []
    for idx, article in enumerate(articles[:max_items], start=1):
        pub = article.pub_date or article.created_at
        lines.append(
            f"{idx}. {article.title} | {pub} | 来源：{article.feed_url}"
        )
    return lines


def generate_report(
    report_type: str,
    *,
    settings: AppSettings,
    ai_client: Optional[AIClient],
    telegram_client: Optional[TelegramClient],
    start_override: Optional[datetime] = None,
    end_override: Optional[datetime] = None,
) -> Optional[int]:
    label_map = {"daily": "日报", "hourly": "小时报"}
    label = label_map.get(report_type)
    if not label:
        logging.warning(f"未知的报告类型：{report_type}")
        return None

    delta_default = timedelta(days=1) if report_type == "daily" else timedelta(hours=1)

    if start_override and end_override:
        start = start_override.astimezone(UTC)
        end = end_override.astimezone(UTC)
    elif start_override or end_override:
        logging.warning("报告生成参数不完整，缺少开始或结束时间")
        return None
    else:
        now_local = datetime.now(BEIJING_TZ)
        if report_type == "daily":
            end_local = _floor_to_day(now_local)
        else:
            end_local = _floor_to_hour(now_local)
        start_local = end_local - delta_default
        start = start_local.astimezone(UTC)
        end = end_local.astimezone(UTC)

    if end <= start:
        logging.debug("报告时间范围非法，跳过")
        return None

    articles = list_articles_in_range(start, end)
    article_count = len(articles)

    timeframe_display = _format_range_local(start, end)
    feed_counts = Counter(a.feed_url for a in articles)
    max_fallback_items = 50 if report_type == "daily" else 30
    article_lines = _build_article_lines(articles, max_fallback_items)

    start_local = start.astimezone(BEIJING_TZ)
    end_local = end.astimezone(BEIJING_TZ)
    report_title = (
        f"RSS-AI 每日汇总（{start_local.strftime('%Y-%m-%d')}）"
        if report_type == "daily"
        else f"RSS-AI 小时汇总（{start_local.strftime('%Y-%m-%d %H:%M')} - {end_local.strftime('%H:%M')}）"
    )

    summary_text: Optional[str] = None
    report_defaults = SettingsReports()
    report_cfg = settings.reports or report_defaults

    timeout_seconds = report_cfg.report_timeout_seconds or report_defaults.report_timeout_seconds
    timeout_seconds = max(10, min(timeout_seconds, 300))

    if ai_client is not None and article_count > 0:
        system_prompt = report_cfg.system_prompt or report_defaults.system_prompt
        article_details = []
        for idx, article in enumerate(articles, start=1):
            article_details.append(
                f"{idx}. 标题：{article.title}\n   来源：{article.feed_url}\n   发布时间：{article.pub_date or article.created_at}\n   摘要：{article.summary_text}"
            )
        feed_stats = "\n".join(
            f"- {feed}: {count} 篇" for feed, count in feed_counts.most_common()
        ) or "- （无文章）"
        article_details_block = "\n".join(article_details) or "(无文章)"
        template = report_cfg.user_prompt_template or report_defaults.user_prompt_template
        try:
            user_prompt = template.format(
                label=label,
                timeframe=timeframe_display,
                article_count=article_count,
                feed_stats=feed_stats,
                article_details=article_details_block,
            )
        except Exception as exc:
            logging.warning("报告用户提示词模板格式化失败，使用默认模板: %s", exc)
            user_prompt = report_defaults.user_prompt_template.format(
                label=label,
                timeframe=timeframe_display,
                article_count=article_count,
                feed_stats=feed_stats,
                article_details=article_details_block,
            )
        try:
            summary_text = ai_client.generate_report(
                report_type=label,
                timeframe=timeframe_display,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                timeout=timeout_seconds,
            )
        except Exception:
            logging.exception("调用AI生成报告失败")
            summary_text = None

    if not summary_text:
        summary_text = _fallback_report_summary(
            label=label,
            timeframe_display=timeframe_display,
            article_count=article_count,
            feed_counts=feed_counts,
            article_lines=article_lines,
        )

    timeframe_start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    timeframe_end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    report = ReportCreate(
        report_type=report_type,
        title=report_title,
        summary_text=summary_text,
        timeframe_start=timeframe_start_str,
        timeframe_end=timeframe_end_str,
        article_count=article_count,
    )
    report_id = insert_report(report)
    logging.info(
        f"生成{label}完成：时间段 {timeframe_display}，文章 {article_count} 篇，ID={report_id}"
    )

    if telegram_client is not None and settings.telegram.enabled:
        header = f"RSS-AI {label}"
        body_lines = [
            header,
            f"时间范围：{timeframe_display}",
            f"文章总数：{article_count}",
            "",
            summary_text,
        ]
        message = "\n".join(body_lines)
        max_len = 3900
        if len(message) > max_len:
            message = message[: max_len - 3] + "..."
            logging.warning("Telegram 报告推送长度超限，已截断处理")
        ok = telegram_client.send_message(
            settings.telegram.chat_id,
            message,
            parse_mode=None,
            disable_web_page_preview=True,
        )
        logging.info(f"推送Telegram {label}：{'成功' if ok else '失败'}")

    return report_id
