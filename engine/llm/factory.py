"""Factory for creating LLM clients from configuration."""

from __future__ import annotations

import os
from typing import Optional

from .base import BaseLLMClient


def create_llm_client(
    backend: str = "deepseek",
    api_key: str = "",
    model: str = "",
    dry_run: bool = False,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client based on the specified backend.

    Args:
        backend: One of "deepseek", "ollama", "claude"
        api_key: API key for cloud services
        model: Model name override
        dry_run: If True, return a DryRunClient that simulates responses (no API key needed)
        **kwargs: Backend-specific options (e.g. ollama_url)

    Returns:
        A configured LLM client instance.

    Raises:
        ValueError: If the backend is unknown or required config is missing.
    """
    if dry_run:
        from .dryrun_client import DryRunClient
        return DryRunClient()

    backend = backend.lower().strip()

    if backend == "deepseek":
        from .deepseek_client import DeepSeekClient
        key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise ValueError("DeepSeek API key required. Set DEEPSEEK_API_KEY env var or pass --api-key")
        return DeepSeekClient(api_key=key, model=model or "deepseek-chat")

    elif backend == "ollama":
        from .ollama_client import OllamaClient
        url = kwargs.get("ollama_url") or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        return OllamaClient(base_url=url, model=model or "deepseek-coder-v2")

    elif backend == "claude":
        from .claude_client import ClaudeClient
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY env var or pass --api-key")
        return ClaudeClient(api_key=key, model=model or "claude-sonnet-4-20250514")

    else:
        raise ValueError(f"Unknown LLM backend: {backend}. Options: deepseek, ollama, claude")
