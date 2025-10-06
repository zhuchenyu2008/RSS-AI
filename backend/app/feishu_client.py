from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional

import httpx


class FeishuClient:
    def __init__(self, webhook_url: str, secret: Optional[str] = None, timeout: float = 20.0):
        self.webhook_url = webhook_url
        self.secret = secret or ""
        self.timeout = timeout

    def _build_payload(self, text: str) -> dict:
        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        if self.secret:
            timestamp = str(int(time.time()))
            string_to_sign = f"{timestamp}\n{self.secret}"
            digest = hmac.new(
                self.secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            payload["timestamp"] = timestamp
            payload["sign"] = base64.b64encode(digest).decode("utf-8")
        return payload

    def send_message(self, text: str) -> bool:
        if not self.webhook_url:
            return False
        payload = self._build_payload(text)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                # 飞书自定义机器人返回 {"StatusCode":0,...}
                return (data.get("StatusCode") == 0) or bool(data.get("code") == 0)
        except Exception:
            return False

