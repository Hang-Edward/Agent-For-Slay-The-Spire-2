from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RewardBreakdown:
    total: float
    components: dict[str, float]
    reward_version: str = "1"


class RewardCalculator:
    def _result(self, components: dict[str, float]) -> RewardBreakdown:
        return RewardBreakdown(round(sum(components.values()), 4), components)

    def transition(self, before: dict, after: dict) -> RewardBreakdown:
        before_enemy = sum(max(0, int(m.get("current_hp", 0))) for m in before.get("monsters", []))
        after_enemy = sum(max(0, int(m.get("current_hp", 0))) for m in after.get("monsters", []))
        before_player = before.get("player", {})
        after_player = after.get("player", {})
        hp_delta = int(after_player.get("current_hp", 0)) - int(before_player.get("current_hp", 0))
        return self._result({
            "player_hp_delta": hp_delta * 2.0,
            "enemy_hp_delta": max(0, before_enemy - after_enemy) * 0.25,
            "floor_progress": max(0, int(after.get("floor", 0)) - int(before.get("floor", 0))) * 5.0,
        })

    def room(self, summary: dict) -> RewardBreakdown:
        return self._result({
            "room_victory": 12.0 if summary.get("won") else -20.0,
            "remaining_hp_ratio": float(summary.get("hp_ratio", 0)) * 5.0,
        })

    def terminal(self, summary: dict) -> RewardBreakdown:
        victory = summary.get("result") == "victory"
        return self._result({
            "run_result": 100.0 if victory else -50.0,
            "floor_progress": float(summary.get("floor", 0)) * 1.5,
        })
