"""Base class for LLM clients.

All LLM backends must implement the `think` method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class LLMRequestError(RuntimeError):
    """模型请求失败；调用方不得直接执行不完整的模型输出。"""


class BaseLLMClient(ABC):
    """Abstract base class for all LLM API clients."""

    @abstractmethod
    def think(self, prompt: str, temperature: float = 0.3, max_tokens: int = 128) -> tuple[str, float]:
        """Send a prompt to the LLM and get a response.

        Returns:
            Tuple of (response_text, elapsed_seconds)
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the client has valid credentials to make API calls."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name of the LLM backend."""
        return self.__class__.__name__
