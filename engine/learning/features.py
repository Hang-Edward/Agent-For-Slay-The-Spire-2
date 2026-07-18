"""从游戏状态和候选中提取数值特征向量，供神经网络策略使用。"""

from __future__ import annotations

import math
from typing import Any

FEATURE_DIM = 48  # 固定特征向量维度


def extract_state_features(state_data: dict) -> list[float]:
    """从 state_data 中提取固定长度的数值特征向量。"""
    feats: list[float] = []
    gs = state_data.get("game_state")
    player = state_data.get("player", {}) if not gs else {
        "current_hp": getattr(gs, "player_hp", 0),
        "max_hp": getattr(gs, "player_max_hp", 0),
        "block": getattr(gs, "player_block", 0),
        "energy": getattr(gs, "player_energy", 0),
        "gold": getattr(gs, "gold", 0),
    }
    monsters = state_data.get("monsters", []) if not gs else [
        {"current_hp": m.current_hp, "max_hp": m.max_hp, "block": m.block,
         "intent_damage": getattr(m, "intent_damage", 0),
         "intent_hits": getattr(m, "intent_hits", 1),
         "is_attacking": getattr(m, "is_attacking", True)}
        for m in getattr(gs, "alive_monsters", [])
    ]
    hand = state_data.get("hand", []) if not gs else [
        {"cost": c.cost_for_turn, "damage": c.damage, "block": c.block,
         "is_playable": c.is_playable, "card_type": c.card_type,
         "has_target": c.has_target}
        for c in getattr(gs, "hand", [])
    ]
    deck = state_data.get("deck", []) if not gs else getattr(gs, "deck", [])

    hp = int(player.get("current_hp", 0))
    max_hp = int(player.get("max_hp", 1))
    block = int(player.get("block", 0))
    energy = int(player.get("energy", 0))

    # ── Player features (12) ──────────────────────────
    feats.append(hp / max(1, max_hp))               # HP ratio
    feats.append(block / max(1, max_hp))             # Block ratio
    feats.append(energy / max(1, 6))                 # Energy (normalized)
    feats.append(int(player.get("gold", 0)) / 500)   # Gold (normalized)
    feats.append(1.0 if hp <= 0 else 0.0)            # Is dead
    feats.append(1.0 if hp / max(1, max_hp) < 0.3 else 0.0)  # Critical HP
    feats.append(1.0 if block >= hp else 0.0)        # Block >= HP (safe)
    feats.append(len(state_data.get("potions", [])) / 3)  # Potion count

    # ── Hand features (10) ────────────────────────────
    playable = [c for c in hand if c.get("is_playable", False)]
    feats.append(len(hand) / 10)                     # Hand size
    feats.append(len(playable) / 10)                 # Playable count
    feats.append(sum(c.get("cost", 0) for c in playable) / max(1, energy))  # Cost/energy ratio
    feats.append(min(1.0, sum(c.get("damage", 0) for c in playable) / 60))  # Total damage in hand
    feats.append(min(1.0, sum(c.get("block", 0) for c in playable) / 60))   # Total block in hand
    feats.append(1.0 if any(c.get("card_type") == "POWER" for c in playable) else 0.0)  # Has power
    feats.append(1.0 if any(c.get("has_target", False) for c in playable) else 0.0)  # Has targetable
    feats.append(len(playable) - len(hand) if hand else 0.0)  # Non-playable diff
    feats.append(min(1.0, sum(c.get("cost", 0) for c in hand) / 10))  # Total cost in hand
    feats.append(min(1.0, max((c.get("cost", 0) for c in playable), default=0) / 5))  # Max playable cost

    # ── Monster features (8) ──────────────────────────
    alive = [m for m in monsters if m.get("current_hp", 0) > 0]
    incoming = sum(m.get("intent_damage", 0) * max(1, m.get("intent_hits", 1)) for m in alive if m.get("is_attacking"))
    feats.append(len(alive) / 5)                     # Monster count
    feats.append(min(1.0, sum(m.get("current_hp", 0) for m in alive) / 200))  # Total HP
    feats.append(min(1.0, incoming / 60))             # Incoming damage
    feats.append(min(1.0, max((m.get("intent_damage", 0) for m in alive), default=0) / 30))  # Max single attack
    feats.append(1.0 if incoming > hp + block else 0.0)  # Lethal threat
    feats.append(1.0 if incoming > block else 0.0)    # Unblocked damage
    feats.append(1.0 if len(alive) > 1 else 0.0)     # Multiple enemies
    feats.append(1.0 if any(m.get("current_hp", 0) <= 10 for m in alive) else 0.0)  # Low HP enemy

    # ── Deck features (6) ─────────────────────────────
    attack_ratio = sum(1 for c in deck if c.get("card_type") == "ATTACK") / max(1, len(deck))
    skill_ratio = sum(1 for c in deck if c.get("card_type") == "SKILL") / max(1, len(deck))
    feats.append(len(deck) / 40)                     # Deck size
    feats.append(attack_ratio)                       # Attack ratio
    feats.append(skill_ratio)                        # Skill ratio
    feats.append(sum(c.get("cost", 0) for c in deck) / max(1, len(deck) * 3))  # Avg cost
    feats.append(1.0 if len(deck) > 25 else 0.0)     # Large deck
    feats.append(1.0 if len(deck) < 5 else 0.0)      # Tiny deck

    # ── Turn/Progress features (6) ────────────────────
    feats.append(int(state_data.get("turn", 0)) / 20)  # Turn normalized
    feats.append(int(state_data.get("floor", 1)) / 60) # Floor normalized
    feats.append(int(state_data.get("act", 1)) / 4)    # Act normalized
    feats.append(1.0 if state_data.get("screen_type") == "COMBAT" else 0.0)
    feats.append(1.0 if state_data.get("decision_ready", False) else 0.0)

    # ── Screen-type one-hot (6) ──────────────────────
    screen = state_data.get("screen_type", "")
    for st in ("COMBAT", "CARD_SELECT", "MAIN_MENU", "MAP", "EVENT", "REWARDS", "REST", "SHOP", "GAME_OVER"):
        feats.append(1.0 if screen == st else 0.0)

    # Pad or truncate to FEATURE_DIM
    if len(feats) < FEATURE_DIM:
        feats.extend([0.0] * (FEATURE_DIM - len(feats)))
    return feats[:FEATURE_DIM]


def extract_candidate_features(candidate: dict, screen_type: str) -> list[float]:
    """从单个候选动作中提取特征向量。"""
    feats: list[float] = []

    if screen_type == "COMBAT":
        cards = candidate.get("cards", [])
        feats.append(len(cards) / 5)                  # Cards in sequence
        feats.append(min(1.0, float(candidate.get("cost", 0)) / 6))  # Total cost
        feats.append(min(1.0, float(candidate.get("damage", 0)) / 60))  # Damage
        feats.append(min(1.0, float(candidate.get("block", 0)) / 60))   # Block
        feats.append(min(1.0, float(candidate.get("estimated_hp_loss", 0)) / 60))  # HP loss
        feats.append(min(1.0, float(candidate.get("damage_avoided_by_kills", 0)) / 60))  # Avoided damage
        feats.append(float(candidate.get("score", 0)) / 100)  # Normalized score
        feats.append(1.0 if candidate.get("block", 0) > 0 else 0.0)  # Has block
        feats.append(1.0 if candidate.get("damage", 0) > 0 else 0.0)  # Has damage
        feats.append(1.0 if candidate.get("estimated_hp_loss", 0) == 0 else 0.0)  # Zero loss
    else:
        kind = str(candidate.get("kind", ""))
        feats.append(float(candidate.get("option_index", 0)) / 20)  # Index normalized
        feats.append(1.0 if kind == "character" else 0.0)
        feats.append(1.0 if kind == "singleplayer" else 0.0)
        feats.append(1.0 if kind == "confirm" else 0.0)
        feats.append(1.0 if kind == "map" else 0.0)
        feats.append(1.0 if kind == "card" else 0.0)
        feats.append(1.0 if kind == "relic" else 0.0)
        feats.append(1.0 if kind == "event" else 0.0)
        feats.append(1.0 if kind == "proceed" else 0.0)
        feats.append(float(candidate.get("score", 0)) / 100)

    # Pad to 12
    while len(feats) < 12:
        feats.append(0.0)
    return feats[:12]


def extract_pair(state_data: dict, candidate: dict) -> list[float]:
    """拼接 state 特征 + candidate 特征 → 用于评分网络的输入向量。"""
    return extract_state_features(state_data) + extract_candidate_features(candidate, state_data.get("screen_type", ""))
