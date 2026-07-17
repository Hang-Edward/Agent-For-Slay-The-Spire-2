"""整回合滚动规划所需的威胁、血量预算和候选序列分析。"""

from __future__ import annotations

from itertools import permutations

from state.game_state import GameState


def analyze_turn(state: GameState) -> dict:
    incoming = sum(mon.intent_damage * max(1, mon.intent_hits) for mon in state.alive_monsters if mon.is_attacking)
    unblocked = max(0, incoming - state.player_block)
    hp_ratio = state.player_hp / max(1, state.player_max_hp)
    if unblocked >= state.player_hp:
        risk = "LETHAL"
    elif hp_ratio < 0.35 or unblocked >= state.player_hp * 0.25:
        risk = "HIGH"
    elif unblocked > 0:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    playable = [(index, card) for index, card in enumerate(state.hand)
                if card.is_playable and card.cost_for_turn <= state.player_energy]
    sequences: list[dict] = []
    # 手牌通常很小；限制长度和候选数，避免排列爆炸。
    for length in range(1, min(5, len(playable)) + 1):
        for sequence in permutations(playable, length):
            cost = sum(max(0, card.cost_for_turn) for _, card in sequence)
            if cost > state.player_energy:
                continue
            damage = sum(card.damage for _, card in sequence)
            block = sum(card.block for _, card in sequence)
            setup = sum(1 for _, card in sequence if card.card_type == "POWER" or card.magic_number > 0)
            # 粗略按最低有效血量分配伤害，估算提前击杀攻击者能避免的伤害。
            damage_budget = damage
            avoided_by_kills = 0
            for monster in sorted(
                (mon for mon in state.alive_monsters if mon.is_attacking),
                key=lambda mon: mon.current_hp + mon.block,
            ):
                effective_hp = monster.current_hp + monster.block
                if damage_budget < effective_hp:
                    continue
                damage_budget -= effective_hp
                avoided_by_kills += monster.intent_damage * max(1, monster.intent_hits)
            incoming_after_kills = max(0, incoming - avoided_by_kills)
            unblocked_after_kills = max(0, incoming_after_kills - state.player_block)
            prevented = min(unblocked_after_kills, block)
            hp_loss = max(0, unblocked_after_kills - block)
            score = (
                damage
                + avoided_by_kills * (2.2 if risk in {"LETHAL", "HIGH"} else 1.5)
                + prevented * (2.0 if risk in {"LETHAL", "HIGH"} else 1.2)
                + setup * 2.0
            )
            if hp_loss >= state.player_hp:
                score -= 1000
            sequences.append({
                "cards": [index for index, _ in sequence],
                "names": [card.name for _, card in sequence],
                "cost": cost,
                "damage": damage,
                "block": block,
                "damage_avoided_by_kills": avoided_by_kills,
                "estimated_hp_loss": hp_loss,
                "score": round(score, 2),
            })
            if len(sequences) >= 1200:
                break
        if len(sequences) >= 1200:
            break
    sequences.sort(key=lambda item: item["score"], reverse=True)
    return {
        "incoming_damage": incoming,
        "unblocked_damage": unblocked,
        "hp_ratio": round(hp_ratio, 3),
        "risk": risk,
        "acceptable_hp_loss": 0 if risk in {"LETHAL", "HIGH"} else max(0, int(state.player_max_hp * 0.08)),
        "candidate_sequences": sequences[:8],
    }
