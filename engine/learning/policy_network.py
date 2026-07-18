"""小策略网络：输入 state+candidate 特征，输出该候选的得分。"""

from __future__ import annotations

import torch
import torch.nn as nn


class PolicyNetwork(nn.Module):
    """小型 MLP 策略网络。

    输入：state_features (48d) + candidate_features (12d) = 60d
    输出：单个分数（该候选动作的优劣）
    """

    def __init__(self, input_dim: int = 60, hidden_dim: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1),
        )
        self._initialize_weights()

    def _initialize_weights(self):
        for m in self.net:
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight, gain=0.5)
                nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """返回每个候选的得分。"""
        return self.net(x).squeeze(-1)


class BehaviorCloneLoss(nn.Module):
    """行为克隆损失：让被选中的候选得分高于未选中的。

    使用 margin-based ranking loss。支持变长候选组（由 batch_sizes 指定）。
    """

    def __init__(self, margin: float = 0.5):
        super().__init__()
        self.margin = margin

    def forward(self, scores: torch.Tensor, chosen_mask: torch.Tensor,
                batch_sizes: torch.Tensor | None = None) -> torch.Tensor:
        """scores: (total_candidates,), chosen_mask: (total_candidates,) boolean。

        每组的选中候选得分应高于同组未选中候选 + margin。
        """
        if batch_sizes is None:
            batch_sizes = torch.tensor([scores.size(0)])

        losses: list[torch.Tensor] = []
        ptr = 0
        for sz in batch_sizes:
            group_scores = scores[ptr:ptr + sz]
            group_chosen = chosen_mask[ptr:ptr + sz]
            ptr += sz

            chosen = group_scores[group_chosen]
            not_chosen = group_scores[~group_chosen]

            if chosen.numel() > 0 and not_chosen.numel() > 0:
                loss = torch.clamp(self.margin + not_chosen - chosen.max(), min=0)
                losses.append(loss.mean())
            elif chosen.numel() == 0 and not_chosen.numel() > 0:
                losses.append(torch.tensor(0.0, device=scores.device))

        if not losses:
            return torch.tensor(0.0, device=scores.device, requires_grad=True)
        return torch.stack(losses).mean()
