from __future__ import annotations

import json
from typing import Optional
import httpx


class AIClient:
    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.2, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def summarize(self, *, title: str, link: str, pub_date: Optional[str], author: Optional[str], content: str) -> Optional[dict]:
        if not self.api_key:
            return None
        url = f"{self.base_url}/v1/chat/completions"

        system = (
            "你是一个中文内容编辑助手。请对RSS文章进行信息抽取与高质量中文摘要，"
            "并输出严格的JSON对象，字段必须为：title, link, pubDate, author, summary_text。"
            "其中：title为原文标题或优化后的标题；link为原始URL；pubDate为发布时间（原文给出即可）；"
            "author为作者（若未知可留空字符串）；summary_text为简洁、条理清晰的段落式中文总结。"
        )
        user = (
            f"标题: {title}\n"
            f"链接: {link}\n"
            f"发布时间: {pub_date or ''}\n"
            f"作者: {author or ''}\n"
            "正文/摘要(可能包含HTML):\n" + (content or "") + "\n\n"
            "请只输出JSON，不要任何解释或markdown。"
        )

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return None

        try:
            content = data["choices"][0]["message"]["content"].strip()
            # Some models may wrap in ```json ... ```
            if content.startswith("```"):
                content = content.strip("`" )
                # remove possible 'json\n'
                if content.lower().startswith("json\n"):
                    content = content[5:]
            obj = json.loads(content)
            # Basic check
            if not isinstance(obj, dict):
                return None
            for k in ["title", "link", "pubDate", "author", "summary_text"]:
                if k not in obj:
                    obj[k] = "" if k != "summary_text" else ""
            # Ensure link is original
            obj["link"] = link
            if not obj.get("title"):
                obj["title"] = title
            if not obj.get("pubDate"):
                obj["pubDate"] = pub_date or ""
            if not obj.get("author"):
                obj["author"] = author or ""
            return obj
        except Exception:
            return None


def fallback_summary(title: str, link: str, pub_date: Optional[str], author: Optional[str], content: str) -> dict:
    # Very simple fallback summarization: strip HTML tags and truncate
    import re

    text = re.sub(r"<[^>]+>", " ", content or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 600:
        text = text[:600] + "…"
    return {
        "title": title,
        "link": link,
        "pubDate": pub_date or "",
        "author": author or "",
        "summary_text": text or "(无摘要)",
    }

