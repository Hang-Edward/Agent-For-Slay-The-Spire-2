"""神经网络策略：用训练好的 MLP 模型替代启发式评分函数。"""

from __future__ import annotations

import os
from time import perf_counter
from typing import Any

import torch

from communication.protocol import Decision
from learning.features import extract_state_features, extract_candidate_features, FEATURE_DIM
from learning.policy_network import PolicyNetwork
from policy.local_policy import LocalPolicy, PolicyResult
from strategy.guardrails import StrategyGuardrail


class NeuralPolicy(LocalPolicy):
    """用训练好的神经网络替代 _automation_priority 和 score 排序。

    保留 LocalPolicy 的决策执行逻辑（_decision_from_candidate），
    但候选排序改用模型评分。"""

    name = "NeuralPolicy"

    def __init__(self, model_path: str = "../data/policy_model.pt",
                 guardrail: StrategyGuardrail | None = None):
        super().__init__(guardrail=guardrail)
        self.model: PolicyNetwork | None = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._load_model(model_path)

    def _load_model(self, model_path: str) -> bool:
        if not os.path.exists(model_path):
            print(f"[NeuralPolicy] Model not found: {model_path}, falling back to heuristic")
            return False
        try:
            self.model = PolicyNetwork(input_dim=FEATURE_DIM + 12).to(self.device)
            self.model.load_state_dict(torch.load(model_path, map_location=self.device, weights_only=True))
            self.model.eval()
            print(f"[NeuralPolicy] Loaded model from {model_path}")
            return True
        except Exception as e:
            print(f"[NeuralPolicy] Failed to load model: {e}, falling back to heuristic")
            self.model = None
            return False

    def _best_candidate(self, candidates: list[dict], state_data: dict | None = None) -> dict | None:
        """用神经网络评分替代启发式优先级 + 分数排序。

        如果模型不可用，回退到父类的启发式方法。
        """
        if not candidates:
            return None
        if self.model is None or state_data is None:
            return super()._best_candidate(candidates)

        try:
            screen_type = state_data.get("screen_type", "")
            state_feat = extract_state_features(state_data)

            # 对每个候选评分
            scored: list[tuple[float, dict]] = []
            with torch.no_grad():
                for cand in candidates:
                    cand_feat = extract_candidate_features(cand, screen_type)
                    combined = torch.tensor(state_feat + cand_feat, dtype=torch.float32, device=self.device).unsqueeze(0)
                    score = self.model(combined).item()
                    scored.append((score, cand))

            # 按模型评分降序排列
            scored.sort(key=lambda x: -x[0])
            return scored[0][1]

        except Exception as e:
            print(f"[NeuralPolicy] Scoring error: {e}, falling back to heuristic")
            return super()._best_candidate(candidates)

    def decide(self, handler, state_data: dict, candidates: list[dict]) -> PolicyResult:
        """重写 decide：传入 state_data 供模型评分。"""
        start = perf_counter()
        selected = self._best_candidate(candidates, state_data)
        decision = self._decision_from_candidate(handler.screen_type, state_data, selected)
        if decision is None:
            decision = handler.fallback_decision(state_data)
        if decision is None:
            decision = Decision.end_turn()

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
