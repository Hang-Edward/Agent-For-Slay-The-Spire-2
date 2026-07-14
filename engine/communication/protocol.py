"""Protocol definitions for communicating with the Mod."""

from typing import Optional


# ─── 屏幕类型常量 ──────────────────────────────────────────
SCREEN_COMBAT = "COMBAT"
SCREEN_CARD_REWARD = "CARD_REWARD"
SCREEN_REST = "REST"
SCREEN_EVENT = "EVENT"
SCREEN_MAP = "MAP"
SCREEN_SHOP = "SHOP"
SCREEN_BOSS_REWARD = "BOSS_REWARD"
SCREEN_TREASURE = "TREASURE"


class Decision:
    """An AI decision to send to the Mod."""

    def __init__(self, action_type: str, hand_index: int = -1,
                 monster_index: int = -1, potion_slot: int = -1,
                 card_index: int = -1, option_index: int = -1):
        self.type = action_type
        # 战斗相关
        self.hand_index = hand_index
        self.monster_index = monster_index
        self.potion_slot = potion_slot
        # 非战斗相关
        self.card_index = card_index      # 卡牌奖励选择
        self.option_index = option_index    # 事件/选项选择

    def to_json(self) -> dict:
        d = {"type": self.type}
        if self.hand_index >= 0:
            d["hand_index"] = self.hand_index
        if self.monster_index >= 0:
            d["monster_index"] = self.monster_index
        if self.potion_slot >= 0:
            d["potion_slot"] = self.potion_slot
        if self.card_index >= 0 or self.type == "pick_card":
            d["card_index"] = self.card_index
        if self.option_index >= 0:
            d["option_index"] = self.option_index
        return d

    def to_llm_format(self) -> str:
        """Format decision for LLM context (showing what was chosen)."""
        if self.type == "end_turn":
            return "END"
        elif self.type == "play_card":
            return f"PLAY {self.hand_index}" + (f" {self.monster_index}" if self.monster_index >= 0 else "")
        elif self.type == "use_potion":
            return f"POTION {self.potion_slot}" + (f" {self.monster_index}" if self.monster_index >= 0 else "")
        elif self.type == "pick_card":
            return f"PICK {self.card_index}" if self.card_index >= 0 else "SKIP"
        elif self.type == "rest":
            return "REST"
        elif self.type == "smith":
            return f"SMITH {self.card_index}"
        elif self.type == "choose_option":
            return f"CHOOSE {self.option_index}"
        return "END"

    # ─── 工厂方法 ──────────────────────────────────────────

    @classmethod
    def play_card(cls, hand_index: int, monster_index: int = 0) -> "Decision":
        return cls("play_card", hand_index=hand_index, monster_index=monster_index)

    @classmethod
    def end_turn(cls) -> "Decision":
        return cls("end_turn")

    @classmethod
    def use_potion(cls, slot: int, target: int = 0) -> "Decision":
        return cls("use_potion", potion_slot=slot, monster_index=target)

    @classmethod
    def pick_card(cls, card_index: int) -> "Decision":
        """选择卡牌奖励中的一张。传入 -1 表示跳过。"""
        return cls("pick_card", card_index=card_index)

    @classmethod
    def skip_reward(cls) -> "Decision":
        """跳过卡牌奖励。"""
        return cls("pick_card", card_index=-1)

    @classmethod
    def rest(cls) -> "Decision":
        """在篝火休息。"""
        return cls("rest")

    @classmethod
    def smith(cls, card_index: int = 0) -> "Decision":
        """在篝火锻造升级一张牌。"""
        return cls("smith", card_index=card_index)

    @classmethod
    def choose_option(cls, option_index: int) -> "Decision":
        """选择事件选项。"""
        return cls("choose_option", option_index=option_index)

    def __repr__(self):
        return self.to_llm_format()
