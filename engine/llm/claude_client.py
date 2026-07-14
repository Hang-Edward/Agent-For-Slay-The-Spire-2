"""Claude (Anthropic) API client."""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests

from .base import BaseLLMClient, LLMRequestError


class ClaudeClient(BaseLLMClient):
    """Client for Anthropic's Claude API."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model

    def think(self, prompt: str, temperature: float = 0.3, max_tokens: int = 128) -> tuple[str, float]:
        start = time.time()
        try:
            resp = requests.post(
                self.API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["content"][0]["text"].strip()
        except Exception as e:
            raise LLMRequestError(f"Claude request failed: {e}") from e

        elapsed = time.time() - start
        return content, elapsed

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def name(self) -> str:
        return f"Claude ({self.model})"
