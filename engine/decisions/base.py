"""决策处理器抽象基类。

所有屏幕类型的决策处理器都继承此类。
每个 Handler 负责：
1. 从原始状态中提取当前屏幕的决策数据
2. 构建 LLM Prompt
3. 解析 LLM 响应为 Decision
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from communication.protocol import Decision


class DecisionHandler(ABC):
    """决策处理器基类。"""

    @property
    @abstractmethod
    def screen_type(self) -> str:
        """此处理器负责的屏幕类型，如 'COMBAT', 'CARD_REWARD' 等。"""
        ...

    def can_handle(self, screen_type: str, raw_state: dict) -> bool:
        """判断此处理器是否能处理当前屏幕。"""
        return screen_type == self.screen_type

    @abstractmethod
    def extract_state(self, raw_state: dict) -> dict:
        """从完整 JSON 状态中提取当前决策需要的数据。

        Args:
            raw_state: 完整游戏状态的原始 JSON dict

        Returns:
            当前屏幕决策所需的精简数据 dict
        """
        ...

    @abstractmethod
    def build_prompt(self, state_data: dict, strategy_instructions: str = "") -> str:
        """构建发给 LLM 的 Prompt。

        Args:
            state_data: extract_state 返回的数据
            strategy_instructions: Skills 系统的策略指令

        Returns:
            完整 Prompt 字符串
        """
        ...

    @abstractmethod
    def parse_response(self, llm_response: str, state_data: dict) -> Decision:
        """解析 LLM 响应为 Decision。

        Args:
            llm_response: LLM 返回的文本
            state_data: extract_state 返回的数据（用于验证索引合法性等）

        Returns:
            Decision 对象
        """
        ...

    def should_act(self, state_data: dict) -> bool:
        """判断当前屏幕下 AI 是否需要做出决策。

        子类可覆盖此方法实现更复杂的条件判断。
        """
        return True

    def try_auto_decision(self, state_data: dict) -> Optional[Decision]:
        """尝试在不调用 LLM 的情况下直接给出决策。

        当只有唯一合法操作时（如只有一张可玩卡牌），子类可覆盖此方法
        直接返回决策，省去一次 LLM 调用。

        Returns:
            Decision 或 None（表示需要 LLM 决策）
        """
        return None

    def fallback_decision(self, state_data: dict) -> Optional[Decision]:
        """模型不可用或输出非法时返回保证流程继续的安全动作。"""
        return self.try_auto_decision(state_data)
