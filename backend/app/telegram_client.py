from __future__ import annotations

from typing import Optional
import httpx


class TelegramClient:
    def __init__(self, bot_token: str, timeout: float = 20.0):
        self.bot_token = bot_token
        self.timeout = timeout

    def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = "HTML", disable_web_page_preview: bool = False) -> bool:
        if not self.bot_token:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return bool(data.get("ok"))
        except Exception:
            return False

