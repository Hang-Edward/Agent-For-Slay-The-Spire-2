"""Dry-run LLM client — 返回固定响应，用于测试管道流程而不需要 API key。"""

from __future__ import annotations

import random
import re
import time

from .base import BaseLLMClient


class DryRunClient(BaseLLMClient):
    """模拟 LLM 客户端，总是返回固定决策。

    用于测试管道完整性和 `--dry-run` 模式。
    """

    # 不同屏幕类型的默认决策
    DEFAULT_DECISIONS = {
        "COMBAT": "PLAY 0 0",
        "CARD_REWARD": "PICK 0",
        "BOSS_REWARD": "PICK 0",
        "REST": "REST",
        "EVENT": "CHOOSE 0",
    }

    def __init__(self, delay_ms: int = 100):
        self.delay_ms = delay_ms
        self.call_count = 0
        self.last_prompt = ""

    def think(self, prompt: str, temperature: float = 0.0, max_tokens: int = 128) -> tuple[str, float]:
        self.call_count += 1
        self.last_prompt = prompt

        # 从 Prompt 中猜测屏幕类型
        decision = self._guess_decision(prompt)

        # 模拟 LLM 延迟
        elapsed = self.delay_ms / 1000.0

        return decision, elapsed

    def is_configured(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "DryRun"

    def _guess_decision(self, prompt: str) -> str:
        """根据 Prompt 内容猜测应该返回什么决策。"""
        if "CHOOSE <index>" in prompt:
            match = re.search(r"\[(\d+)\]\s+\[AVAILABLE\]", prompt)
            return f"CHOOSE {match.group(1)}" if match else "CHOOSE 0"
        if "=== " in prompt and "===" in prompt:
            # 事件屏幕
            return "CHOOSE 0"
        if "Reward Cards" in prompt or "PICK" in prompt:
            # 卡牌奖励
            return "PICK 0"
        if "REST" in prompt and "SMITH" in prompt:
            # 篝火
            return "REST"
        if "PLAY" in prompt and "monster" in prompt.lower():
            # 战斗 - 打第一张可玩卡牌
            return "PLAY 0 0"
        return "END"

    def reset(self):
        """重置调用计数。"""
        self.call_count = 0
        self.last_prompt = ""
