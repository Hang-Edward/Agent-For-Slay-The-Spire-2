"""DeepSeek V4 Flash API client for AI decision making."""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests

from .base import BaseLLMClient, LLMRequestError


class DeepSeekClient(BaseLLMClient):
    """Client for DeepSeek API."""

    API_URL = "https://api.deepseek.com/v1/chat/completions"

    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-v4-flash"):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model
        self.last_response = ""
        self.last_raw = ""

    def think(self, prompt: str, temperature: float = 0.3, max_tokens: int = 128) -> tuple[str, float]:
        """Send a prompt to DeepSeek and get the response."""
        start = time.time()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            # 实时打牌需要稳定返回最终动作；本地策略层已完成整回合枚举与评分。
            "thinking": {"type": "disabled"},
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            resp = requests.post(
                self.API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if not content:
                finish_reason = data["choices"][0].get("finish_reason", "unknown")
                raise ValueError(f"empty model content (finish_reason={finish_reason})")
            self.last_response = content
            self.last_raw = json.dumps(data, indent=2)
        except Exception as e:
            self.last_response = ""
            self.last_raw = str(e)
            raise LLMRequestError(f"DeepSeek request failed: {e}") from e

        elapsed = time.time() - start
        return content, elapsed

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def name(self) -> str:
        return f"DeepSeek ({self.model})"
