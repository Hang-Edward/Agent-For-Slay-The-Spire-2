"""Protocol definitions for communicating with the Mod."""

from typing import Optional


class Decision:
    """An AI decision to send to the Mod."""

    def __init__(self, action_type: str, hand_index: int = -1,
                 monster_index: int = -1, potion_slot: int = -1):
        self.type = action_type  # "play_card", "end_turn", "use_potion"
        self.hand_index = hand_index
        self.monster_index = monster_index
        self.potion_slot = potion_slot

    def to_json(self) -> dict:
        d = {"type": self.type}
        if self.hand_index >= 0:
            d["hand_index"] = self.hand_index
        if self.monster_index >= 0:
            d["monster_index"] = self.monster_index
        if self.potion_slot >= 0:
            d["potion_slot"] = self.potion_slot
        return d

    def to_llm_format(self) -> str:
        """Format decision for LLM context (showing what was chosen)."""
        if self.type == "end_turn":
            return "END"
        elif self.type == "play_card":
            return f"PLAY {self.hand_index}" + (f" {self.monster_index}" if self.monster_index >= 0 else "")
        elif self.type == "use_potion":
            return f"POTION {self.potion_slot}" + (f" {self.monster_index}" if self.monster_index >= 0 else "")
        return "END"

    @classmethod
    def play_card(cls, hand_index: int, monster_index: int = 0) -> "Decision":
        return cls("play_card", hand_index=hand_index, monster_index=monster_index)

    @classmethod
    def end_turn(cls) -> "Decision":
        return cls("end_turn")

    @classmethod
    def use_potion(cls, slot: int, target: int = 0) -> "Decision":
        return cls("use_potion", potion_slot=slot, monster_index=target)

    def __repr__(self):
        return self.to_llm_format()
