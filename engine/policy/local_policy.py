"""本地即时策略。

这个策略负责低延迟地把已经评分的候选动作转成游戏动作。DeepSeek 可以在
后续作为老师复盘这些选择，但实时出牌不再依赖 API 调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from communication.protocol import Decision


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    response: str
    selected_candidate: dict | None
    elapsed_ms: int


class LocalPolicy:
    """基于本地候选评分选择动作，作为小模型接入前的可替换策略层。"""

    name = "LocalPolicy"

    def decide(self, handler, state_data: dict, candidates: list[dict]) -> PolicyResult:
        start = perf_counter()
        selected = self._best_candidate(candidates)
        decision = self._decision_from_candidate(handler.screen_type, state_data, selected)
        if decision is None:
            decision = handler.fallback_decision(state_data)
        if decision is None:
            decision = Decision.end_turn()
        elapsed_ms = int((perf_counter() - start) * 1000)
        return PolicyResult(
            decision=decision,
            response=decision.to_llm_format(),
            selected_candidate=selected,
            elapsed_ms=elapsed_ms,
        )

    def _best_candidate(self, candidates: list[dict]) -> dict | None:
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (
                float(item.get("final_score", item.get("score", 0.0))),
                -int(item.get("option_index", 9999)),
            ),
        )

    def _decision_from_candidate(self, screen_type: str, state_data: dict,
                                 candidate: dict | None) -> Decision | None:
        if not candidate:
            return None
        if screen_type == "COMBAT":
            cards = candidate.get("cards") or []
            if not cards:
                return None
            hand_index = int(cards[0])
            game_state = state_data.get("game_state")
            card = game_state.hand[hand_index] if game_state and hand_index < len(game_state.hand) else None
            if card is not None and not card.has_target:
                return Decision.play_card(hand_index, -1)
            target = self._weakest_target_index(game_state)
            return Decision.play_card(hand_index, target)
        if "option_index" in candidate:
            return Decision.choose_option(int(candidate["option_index"]))
        return None

    def _weakest_target_index(self, game_state) -> int:
        if not game_state:
            return 0
        targets = getattr(game_state, "targetable_monsters", []) or []
        if not targets:
            return 0
        monster = min(targets, key=lambda item: item.current_hp + item.block)
        return monster.target_index if monster.target_index >= 0 else targets.index(monster)
