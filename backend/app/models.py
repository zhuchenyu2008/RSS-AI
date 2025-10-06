from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class HealthResponse(BaseModel):
    status: str = "ok"


class SettingsFetch(BaseModel):
    interval_minutes: int = Field(10, ge=1, le=24 * 60)
    max_items: int = Field(500, ge=10, le=50000)
    feeds: List[str] = Field(default_factory=list)
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


class SettingsFeishu(BaseModel):
    enabled: bool = False
    webhook_url: str = ""
    secret: str = ""
    push_summary: bool = False


class SettingsLogging(BaseModel):
    level: str = "INFO"
    file: str = "logs/app.log"


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 3601


class AppSettings(BaseModel):
    server: ServerSettings = ServerSettings()
    fetch: SettingsFetch = SettingsFetch()
    ai: SettingsAI = SettingsAI()
    telegram: SettingsTelegram = SettingsTelegram()
    feishu: SettingsFeishu = SettingsFeishu()
    logging: SettingsLogging = SettingsLogging()


class ArticleInDB(BaseModel):
    id: int
    feed_url: str
    item_uid: str
    title: str
    link: str
    pub_date: Optional[str] = None
    author: Optional[str] = None
    summary_text: str
    created_at: str


class ArticleCreate(BaseModel):
    feed_url: str
    item_uid: str
    title: str
    link: str
    pub_date: Optional[str] = None
    author: Optional[str] = None
    summary_text: str


class ArticleListResponse(BaseModel):
    total: int
    items: List[ArticleInDB]


class FetchRequest(BaseModel):
    force: bool = False


class FetchResponse(BaseModel):
    fetched_feeds: int
    new_items: int
    processed_items: int
    message: str = ""
