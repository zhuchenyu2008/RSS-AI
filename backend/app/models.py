from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class HealthResponse(BaseModel):
    status: str = "ok"


class SettingsFetch(BaseModel):
    interval_minutes: int = Field(10, ge=1, le=24 * 60)
    max_items: int = Field(500, ge=10, le=50000)
    feeds: List[str] = Field(default_factory=list)


class SettingsAI(BaseModel):
    enabled: bool = True
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.2


class SettingsTelegram(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


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

