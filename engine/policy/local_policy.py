"""本地即时策略 + 策略护栏。

这个策略负责低延迟地把已经评分的候选动作转成游戏动作。DeepSeek 可以在
后续作为老师复盘这些选择，但实时出牌不再依赖 API 调用。

策略护栏 (StrategyGuardrail) 在决策前后两次拦截：
1. 候选筛选后用护栏检查关键错误（如致命伤害不挡牌）
2. 最终决策发出前再次检查全局规则（如跳过奖励、选禁用选项）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

from communication.protocol import Decision
from strategy.guardrails import GuardrailReport, InterventionLevel, StrategyGuardrail


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    response: str
    selected_candidate: dict | None
    elapsed_ms: int
    guardrail: GuardrailReport | None = None


class LocalPolicy:
    """基于本地候选评分选择动作，作为小模型接入前的可替换策略层。"""

    name = "LocalPolicy"

    def __init__(self, guardrail: StrategyGuardrail | None = None):
        self._guardrail = guardrail or StrategyGuardrail()

    def decide(self, handler, state_data: dict, candidates: list[dict]) -> PolicyResult:
        start = perf_counter()
        selected = self._best_candidate(candidates)
        decision = self._decision_from_candidate(handler.screen_type, state_data, selected)
        if decision is None:
            decision = handler.fallback_decision(state_data)
        if decision is None:
            decision = Decision.end_turn()

        # 护栏检查：在决策发出前检查领域规则
        report = self._guardrail.check(
            screen_type=handler.screen_type,
            decision=decision,
            state_data=state_data,
            candidates=candidates,
        )
        final_decision = report.final_decision or decision

        elapsed_ms = int((perf_counter() - start) * 1000)
        return PolicyResult(
            decision=final_decision,
            response=final_decision.to_llm_format(),
            selected_candidate=selected,
            elapsed_ms=elapsed_ms,
            guardrail=report if report.has_intervention() else None,
        )

    def _best_candidate(self, candidates: list[dict]) -> dict | None:
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (
                self._automation_priority(item),
                float(item.get("final_score", item.get("score", 0.0))),
                -int(item.get("option_index", 9999)),
            ),
        )

    def _automation_priority(self, candidate: dict) -> float:
        if candidate.get("executed_previously"):
            return -500.0
        if candidate.get("stalled_previously"):
            return -400.0
        text = " ".join(
            str(candidate.get(key, ""))
            for key in ("kind", "id", "name", "description", "action_key")
        ).lower()
        if any(token in text for token in (
            "quit", "exit", "settings", "option", "compendium", "credits",
            "multiplayer", "多人", "reset", "重置", "display", "monitor",
            "dropdown", "invite", "邀请",
        )):
            return -100.0
        if "continue_run" in text:
            return 55.0
        if any(token in text for token in ("confirm", "confirmbutton", "确认", "start", "begin", "embark", "ready")):
            return 50.0
        if any(token in text for token in ("standard", "标准", "new run")):
            return 40.0
        if any(token in text for token in ("singleplayer", "single player", "单人模式")):
            return 35.0
        if "charselectbutton" in text:
            return 34.5
        if any(token in text for token in ("ironclad", "铁甲")):
            return 34.0
        if any(token in text for token in ("ironclad", "character", "select")):
            return 30.0
        if "continue" in text or "resume" in text:
            return 25.0
        if "proceed" in text:
            return 10.0
        return 0.0

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
