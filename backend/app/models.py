from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl


class HealthResponse(BaseModel):
    status: str = "ok"


class SettingsFetch(BaseModel):
    interval_minutes: int = Field(10, ge=1, le=24 * 60)
    max_items: int = Field(500, ge=10, le=50000)
    feeds: List[str] = Field(default_factory=list)
    filter_keywords: List[str] = Field(default_factory=list)
    use_article_page: bool = True
    article_timeout_seconds: int = Field(15, ge=5, le=60)
    per_feed_limit: int = Field(20, ge=1, le=1000)


class SettingsAI(BaseModel):
    enabled: bool = True
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    system_prompt: str = (
        "你是一个中文内容编辑助手。请对RSS文章进行信息抽取与高质量中文摘要，并输出严格的JSON对象，"
        "字段必须为：title, link, pubDate, author, summary_text。其中：title为原文标题或优化后的标题；"
        "link为原始URL；pubDate为发布时间（原文给出即可）；author为作者（若未知可留空字符串）；"
        "summary_text为简洁、条理清晰的段落式中文总结。务必只输出JSON，不要任何解释或markdown。"
    )
    user_prompt_template: str = (
        "标题: {title}\n"
        "链接: {link}\n"
        "发布时间: {pub_date}\n"
        "作者: {author}\n"
        "正文/摘要(可能包含HTML):\n{content}\n\n"
        "请只输出JSON，不要任何解释或markdown。"
    )


class SettingsTelegram(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    push_summary: bool = False


class SettingsReports(BaseModel):
    daily_enabled: bool = False
    hourly_enabled: bool = False
    report_timeout_seconds: int = Field(60, ge=10, le=300)
    system_prompt: str = (
        "你是一名资深中文资讯编辑，需要汇总给定时间范围内的RSS内容。"
        "请输出结构化的纯文本报告，包含以下部分：\n"
        "1. 概览：总结整体趋势、领域，给出文章总量。\n"
        "2. 重点事件：列出2-6条最值得关注的资讯，每条1-2句话。\n"
        "3. 数据统计：概括主要来源及数量，指出值得注意的变化。\n"
        "4. 建议：如有必要提出关注方向。\n"
        "输出使用中文，避免Markdown或HTML。"
    )
    user_prompt_template: str = (
        "请基于以下信息生成报告，输出时直接从“概览”部分开始，"
        "不要重复报告类型、时间范围或文章总数等字段。\n\n"
        "报告元信息：\n"
        "- 报告类型：{label}\n"
        "- 时间范围：{timeframe}\n"
        "- 文章总数：{article_count}\n\n"
        "来源统计：\n{feed_stats}\n\n"
        "文章详情（按时间排序）：\n{article_details}"
    )


class SettingsLogging(BaseModel):
    level: str = "INFO"
    file: str = "logs/app.log"


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 3601


class SettingsSecurity(BaseModel):
    admin_password: str = "1234"


class AppSettings(BaseModel):
    server: ServerSettings = ServerSettings()
    fetch: SettingsFetch = SettingsFetch()
    ai: SettingsAI = SettingsAI()
    telegram: SettingsTelegram = SettingsTelegram()
    reports: SettingsReports = SettingsReports()
    logging: SettingsLogging = SettingsLogging()
    security: SettingsSecurity = SettingsSecurity()


class ArticleInDB(BaseModel):
    id: int
    feed_url: str
    item_uid: str
    title: str
    link: str
    pub_date: Optional[str] = None
    author: Optional[str] = None
    summary_text: str
    matched_keywords: List[str] = Field(default_factory=list)
    created_at: str


class ArticleCreate(BaseModel):
    feed_url: str
    item_uid: str
    title: str
    link: str
    pub_date: Optional[str] = None
    author: Optional[str] = None
    summary_text: str
    matched_keywords: List[str] = Field(default_factory=list)


class ArticleListResponse(BaseModel):
    total: int
    items: List[ArticleInDB]


class ReportInDB(BaseModel):
    id: int
    report_type: str
    title: str
    summary_text: str
    timeframe_start: str
    timeframe_end: str
    article_count: int
    created_at: str


class ReportCreate(BaseModel):
    report_type: str
    title: str
    summary_text: str
    timeframe_start: str
    timeframe_end: str
    article_count: int


class ReportListResponse(BaseModel):
    total: int
    items: List[ReportInDB]


class ReportGenerateRequest(BaseModel):
    report_type: Literal["daily", "hourly"]


class FetchRequest(BaseModel):
    force: bool = False


class FetchResponse(BaseModel):
    fetched_feeds: int
    new_items: int
    processed_items: int
    message: str = ""


class UpdateSettingsRequest(BaseModel):
    settings: AppSettings
    password: str
    new_password: Optional[str] = None
