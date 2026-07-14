"""Ollama client for local LLM inference."""

from __future__ import annotations

import json
import time
from typing import Optional

import requests

from .base import BaseLLMClient, LLMRequestError


class OllamaClient(BaseLLMClient):
    """Client for locally running Ollama models."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "deepseek-coder-v2"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.session = requests.Session()

    def think(self, prompt: str, temperature: float = 0.3, max_tokens: int = 128) -> tuple[str, float]:
        start = time.time()
        try:
            resp = self.session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("response", "").strip()
        except Exception as e:
            raise LLMRequestError(f"Ollama request failed: {e}") from e

        elapsed = time.time() - start
        return content, elapsed

    def is_configured(self) -> bool:
        try:
            resp = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    @property
    def name(self) -> str:
        return f"Ollama ({self.model})"
