#!/usr/bin/env python3
"""行为克隆训练脚本：加载 transitions → 特征化 → 训练策略网络 → 导出权重。"""

from __future__ import annotations

import glob
import json
import math
import os
import sys
import time
from typing import Any

import torch
from torch.utils.data import Dataset, DataLoader

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning.features import extract_state_features, extract_candidate_features, FEATURE_DIM
from learning.policy_network import PolicyNetwork, BehaviorCloneLoss


class TransitionDataset(Dataset):
    """加载 transitions.jsonl 文件作为训练数据集。"""

    def __init__(self, data_dir: str, min_score_diff: float = 0.01):
        self.samples: list[dict] = []
        for path in sorted(glob.glob(os.path.join(data_dir, "*/transitions.jsonl"))):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    trans = json.loads(line)
                    # 只使用 policy 或 auto 来源的决策，跳过 fallback
                    if trans.get("source") == "fallback":
                        continue
                    candidates = trans.get("candidates", [])
                    if not candidates:
                        continue
                    chosen = trans.get("chosen_action", {})
                    # 找到被选中的候选索引（by action matching）
                    chosen_idx = self._match_chosen(candidates, chosen, trans.get("pre_state", {}).get("screen_type", ""))
                    if chosen_idx is None:
                        continue
                    self.samples.append({
                        "state_data": trans["pre_state"],
                        "candidates": candidates,
                        "chosen_idx": chosen_idx,
                        "screen_type": trans["pre_state"].get("screen_type", ""),
                        "guardrail": trans.get("guardrail"),
                    })
        print(f"Loaded {len(self.samples)} transitions from {data_dir}")

    @staticmethod
    def _match_chosen(candidates: list[dict], chosen: dict, screen_type: str) -> int | None:
        """找出在 candidates 中对应 chosen_action 的索引。"""
        if screen_type == "COMBAT":
            chosen_type = chosen.get("type", "")
            if chosen_type == "play_card":
                hi = chosen.get("hand_index", -1)
                for i, c in enumerate(candidates):
                    cards = c.get("cards", [])
                    if cards and int(cards[0]) == hi:
                        return i
            elif chosen_type == "end_turn":
                for i, c in enumerate(candidates):
                    cards = c.get("cards", [])
                    if not cards:
                        return i
                return 0
            elif chosen_type == "use_potion":
                for i, c in enumerate(candidates):
                    if c.get("action_key", "").startswith("potion:"):
                        return i
                return 0
            # 默认选第一个
            return 0
        else:
            chosen_option = chosen.get("option_index", -1)
            for i, c in enumerate(candidates):
                ci = c.get("option_index", -1)
                if ci == chosen_option:
                    return i
            # 回退：按 action_key 匹配
            chosen_key = f"choice:{chosen_option}" if chosen_option >= 0 else ""
            if chosen_key:
                for i, c in enumerate(candidates):
                    if c.get("action_key") == chosen_key:
                        return i
            return 0

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        return self.samples[idx]


def collate_batch(batch: list[dict]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """将一批样本整理为 (state_feats, candidate_feats, chosen_mask)。"""
    state_feats_list: list[list[float]] = []
    cand_feats_list: list[list[float]] = []
    chosen_list: list[int] = []
    batch_sizes: list[int] = []

    for sample in batch:
        sf = extract_state_features(sample["state_data"])
        candidates = sample["candidates"]
        chosen_idx = sample["chosen_idx"]
        screen_type = sample["screen_type"]

        # 按 guardrail 修正：如果存在 guardrail 干预，那被修正的候选才是"正确"选择
        guardrail = sample.get("guardrail")
        if guardrail and isinstance(guardrail, dict) and guardrail.get("interventions"):
            # 如果有 guardrail 纠正，找到纠正后的动作对应的候选
            pass  # 保持原始 chosen_idx，guardrail 纠正的是最终决策

        for ci, cand in enumerate(candidates):
            cf = extract_candidate_features(cand, screen_type)
            cand_feats_list.append(cf)
            state_feats_list.append(sf)  # 每个候选共享同一个 state 特征
            if ci == chosen_idx:
                chosen_list.append(1)
            else:
                chosen_list.append(0)
        batch_sizes.append(len(candidates))

    # 同一 batch 内候选数量可能不同，padding 到最多
    max_candidates = max(batch_sizes)
    n_total = sum(batch_sizes)

    state_tensor = torch.zeros((n_total, FEATURE_DIM), dtype=torch.float32)
    cand_tensor = torch.zeros((n_total, 12), dtype=torch.float32)
    chosen_tensor = torch.zeros(n_total, dtype=torch.bool)

    idx = 0
    for i in range(len(batch)):
        sz = batch_sizes[i]
        for j in range(sz):
            state_tensor[idx] = torch.tensor(state_feats_list[idx], dtype=torch.float32)
            cand_tensor[idx] = torch.tensor(cand_feats_list[idx], dtype=torch.float32)
            chosen_tensor[idx] = bool(chosen_list[idx])
            idx += 1

    combined = torch.cat([state_tensor, cand_tensor], dim=1)
    return combined, chosen_tensor, torch.tensor(batch_sizes)


def train(
    data_dir: str = "data/training/runs",
    model_path: str = "data/policy_model.pt",
    epochs: int = 50,
    batch_size: int = 32,
    lr: float = 0.001,
    val_split: float = 0.1,
):
    """训练策略网络并导出权重。"""
    dataset = TransitionDataset(data_dir)

    if len(dataset) < 10:
        print(f"Not enough data ({len(dataset)} samples), skipping training")
        return

    # 训练/验证分割
    n_val = max(1, int(len(dataset) * val_split))
    n_train = len(dataset) - n_val
    train_ds, val_ds = torch.utils.data.random_split(dataset, [n_train, n_val])

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, collate_fn=collate_batch)
    val_loader = DataLoader(val_ds, batch_size=batch_size, collate_fn=collate_batch)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = PolicyNetwork(input_dim=FEATURE_DIM + 12).to(device)
    criterion = BehaviorCloneLoss(margin=0.5)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    print(f"Training on {device}: {n_train} train, {n_val} val samples")
    best_val_loss = float("inf")

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        train_batches = 0

        for combined, chosen, sizes in train_loader:
            combined = combined.to(device)
            chosen = chosen.to(device)

            scores = model(combined)
            loss = criterion(scores, chosen, sizes.to(device))

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            train_loss += loss.item()
            train_batches += 1

        # 验证
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for combined, chosen, sizes in val_loader:
                combined = combined.to(device)
                chosen = chosen.to(device)

                scores = model(combined)
                loss = criterion(scores, chosen, sizes.to(device))
                val_loss += loss.item()

                # 准确率：每个样本组中最高分的候选是否为选中候选
                ptr = 0
                for sz in sizes:
                    group_scores = scores[ptr:ptr + sz]
                    group_chosen = chosen[ptr:ptr + sz]
                    if group_scores.argmax().item() == group_chosen.nonzero(as_tuple=True)[0].item():
                        val_correct += 1
                    val_total += 1
                    ptr += sz

        val_loss /= max(1, len(val_loader))
        accuracy = val_correct / max(1, val_total)
        scheduler.step()

        if (epoch + 1) % 10 == 0 or epoch == 0 or val_loss < best_val_loss:
            print(f"Epoch {epoch+1}/{epochs}: train_loss={train_loss/max(1,train_batches):.4f} "
                  f"val_loss={val_loss:.4f} val_acc={accuracy:.3f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), model_path)
            print(f"  → Saved best model to {model_path} (val_loss={val_loss:.4f})")

    print(f"Training complete. Best model: {model_path} (val_loss={best_val_loss:.4f})")


def main():
    """CLI 入口。"""
    import argparse
    parser = argparse.ArgumentParser(description="Train behavior cloning policy")
    parser.add_argument("--data-dir", default="data/training/runs")
    parser.add_argument("--model-path", default="data/policy_model.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=0.001)
    args = parser.parse_args()

    train(
        data_dir=args.data_dir,
        model_path=args.model_path,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )


if __name__ == "__main__":
    main()
