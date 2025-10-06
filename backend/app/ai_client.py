from __future__ import annotations

import json
import logging
from typing import Optional

import httpx


class AIClient:
    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.2, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def _chat_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def summarize(
        self,
        *,
        title: str,
        link: str,
        pub_date: Optional[str],
        author: Optional[str],
        content: str,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None,
    ) -> Optional[dict]:
        if not self.api_key:
            logging.info("AI 未配置 api_key，跳过AI总结，使用降级摘要")
            return None
        url = self._chat_url()

        system = system_prompt or (
            "你是一个中文内容编辑助手。请对RSS文章进行信息抽取与高质量中文摘要，并输出严格的JSON对象，"
            "字段必须为：title, link, pubDate, author, summary_text。其中：title为原文标题或优化后的标题；"
            "link为原始URL；pubDate为发布时间（原文给出即可）；author为作者（若未知可留空字符串）；"
            "summary_text为简洁、条理清晰的段落式中文总结。务必只输出JSON，不要任何解释或markdown。"
        )
        if user_prompt_template:
            try:
                user = user_prompt_template.format(
                    title=title,
                    link=link,
                    pub_date=pub_date or "",
                    author=author or "",
                    content=content or "",
                )
            except Exception as e:
                logging.warning(f"用户提示词模板格式化失败，改用默认模板: {e}")
                user = (
                    f"标题: {title}\n链接: {link}\n发布时间: {pub_date or ''}\n作者: {author or ''}\n正文/摘要(可能包含HTML):\n{content or ''}\n\n请只输出JSON，不要任何解释或markdown。"
                )
        else:
            user = (
                f"标题: {title}\n链接: {link}\n发布时间: {pub_date or ''}\n作者: {author or ''}\n正文/摘要(可能包含HTML):\n{content or ''}\n\n请只输出JSON，不要任何解释或markdown。"
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
                logging.info(f"AI请求: url={url} model={self.model}")
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    logging.warning(f"AI请求失败 status={resp.status_code} body={resp.text[:200]}")
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logging.warning(f"AI请求异常: {e}")
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
            # usage tokens if present
            usage = data.get("usage") if isinstance(data, dict) else None
            if isinstance(usage, dict):
                meta = {
                    "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                }
                obj["_ai_usage"] = meta
            return obj
        except Exception as e:
            logging.warning(f"AI响应解析失败: {e}")
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
