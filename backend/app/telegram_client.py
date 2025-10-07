from __future__ import annotations

import logging
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
            "disable_web_page_preview": disable_web_page_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                if resp.status_code >= 400:
                    logging.warning(
                        "Telegram API 调用失败 status=%s body=%s",
                        resp.status_code,
                        resp.text[:300],
                    )
                resp.raise_for_status()
                data = resp.json()
                ok = bool(data.get("ok"))
                if not ok:
                    logging.warning("Telegram API 返回失败响应: %s", data)
                return ok
        except Exception as exc:
            logging.warning("Telegram API 请求异常: %s", exc)
            return False
