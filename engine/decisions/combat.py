"""战斗决策处理器 — 处理 COMBAT 屏幕的卡牌出牌决策。"""

from __future__ import annotations

from state.game_state import GameState
from llm.prompt_builder import build_combat_prompt
from llm.response_parser import InvalidDecisionError, parse_llm_response
from communication.protocol import Decision
from strategy.combat_planner import analyze_turn

from typing import Optional

from .base import DecisionHandler


class CombatHandler(DecisionHandler):
    """战斗内决策处理器。"""

    @property
    def screen_type(self) -> str:
        return "COMBAT"

    def extract_state(self, raw_state: dict) -> dict:
        """从原始 JSON 中提取战斗所需数据。"""
        game_state = GameState.from_json(raw_state)
        playable = [
            (i, c) for i, c in enumerate(game_state.hand)
            if c.is_playable and c.cost_for_turn <= game_state.player_energy
        ]
        return {
            "game_state": game_state,
            "turn_plan": analyze_turn(game_state),
            "playable_cards": playable,
            "has_playable_cards": len(playable) > 0,
            "has_alive_monsters": len(game_state.alive_monsters) > 0,
        }

    def build_prompt(self, state_data: dict, strategy_instructions: str = "") -> str:
        game_state = state_data["game_state"]
        return build_combat_prompt(game_state, strategy_instructions, state_data["turn_plan"])

    def parse_response(self, llm_response: str, state_data: dict) -> Decision:
        decision = parse_llm_response(llm_response)
        game_state = state_data["game_state"]
        valid_targets = {
            monster.target_index if monster.target_index >= 0 else index
            for index, monster in enumerate(game_state.targetable_monsters)
        }

        if decision.type == "play_card":
            if not 0 <= decision.hand_index < len(game_state.hand):
                raise InvalidDecisionError(f"hand index out of range: {decision.hand_index}")
            card = game_state.hand[decision.hand_index]
            if not card.is_playable or card.cost_for_turn > game_state.player_energy:
                raise InvalidDecisionError(f"card is not playable: {decision.hand_index}")
            if card.has_target and decision.monster_index not in valid_targets:
                raise InvalidDecisionError(f"monster target is invalid: {decision.monster_index}")

        if decision.type == "use_potion":
            potion = next(
                (p for p in game_state.potions if p and p.get("slot") == decision.potion_slot),
                None,
            )
            if not potion or not potion.get("can_use", False):
                raise InvalidDecisionError(f"potion slot is not usable: {decision.potion_slot}")
            if potion.get("target_type") == "AnyEnemy" and decision.monster_index not in valid_targets:
                raise InvalidDecisionError(f"potion target is invalid: {decision.monster_index}")

        return decision

    def should_act(self, state_data: dict) -> bool:
        game_state = state_data["game_state"]
        return game_state.decision_ready and state_data["has_alive_monsters"]

    def try_auto_decision(self, state_data: dict) -> Optional[Decision]:
        """没有合法牌时自动结束；其余情况交给整回合规划决定是否值得出牌。"""
        playable = state_data.get("playable_cards", [])
        if len(playable) == 0:
            return Decision.end_turn()
        return None

    def fallback_decision(self, state_data: dict) -> Optional[Decision]:
        """仅在模型失败时选择合法牌，避免非法索引让整局永久停住。"""
        playable = state_data.get("playable_cards", [])
        if not playable:
            return Decision.end_turn()

        game_state = state_data["game_state"]
        targets = game_state.targetable_monsters
        target = min(targets, key=lambda monster: monster.current_hp) if targets else None
        target_index = (
            target.target_index if target is not None and target.target_index >= 0 else 0
        )

        # 优先打出费用较高的合法牌，减少因剩余能量不足造成的空转。
        hand_index, _card = max(
            playable,
            key=lambda item: (item[1].cost_for_turn, -item[0]),
        )
        return Decision.play_card(hand_index, target_index)
