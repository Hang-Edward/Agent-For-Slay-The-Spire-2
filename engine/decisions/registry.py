"""屏幕类型到决策处理器的注册表。"""

from __future__ import annotations

from typing import Optional

from .base import DecisionHandler
from .combat import CombatHandler
from .card_reward import CardRewardHandler
from .rest_site import RestSiteHandler
from .event import EventHandler
from .generic_choice import GenericChoiceHandler


class DecisionRegistry:
    """管理所有 DecisionHandler 并根据屏幕类型分派。"""

    def __init__(self):
        self._handlers: dict[str, DecisionHandler] = {}
        self._choice_handler = GenericChoiceHandler()

    def register(self, handler: DecisionHandler, aliases: Optional[list[str]] = None):
        """注册一个处理器。

        Args:
            handler: 决策处理器实例
            aliases: 可选的额外屏幕类型别名（如 BOSS_REWARD）
        """
        self._handlers[handler.screen_type] = handler
        if aliases:
            for alias in aliases:
                self._handlers[alias] = handler

    def get_handler(self, screen_type: str) -> Optional[DecisionHandler]:
        """根据屏幕类型获取对应的处理器。"""
        return self._handlers.get(screen_type)

    def get_handler_for_state(self, raw_state: dict) -> Optional[DecisionHandler]:
        """根据状态数据找到匹配的处理器。"""
        screen_type = raw_state.get("screen_type", "")
        if not screen_type:
            return None
        if raw_state.get("options") and self._choice_handler.can_handle(screen_type, raw_state):
            return self._choice_handler
        handler = self.get_handler(screen_type)
        if handler and handler.can_handle(screen_type, raw_state):
            return handler
        return None

    @property
    def supported_screens(self) -> list[str]:
        """返回所有支持的屏幕类型列表。"""
        return list(self._handlers.keys())


# 全局默认注册表
_default_registry: Optional[DecisionRegistry] = None


def get_default_registry() -> DecisionRegistry:
    """获取默认注册表（含所有内置处理器）。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = DecisionRegistry()
        _default_registry.register(CombatHandler())
        _default_registry.register(CardRewardHandler(), aliases=["BOSS_REWARD"])
        _default_registry.register(RestSiteHandler())
        _default_registry.register(EventHandler())
    return _default_registry
