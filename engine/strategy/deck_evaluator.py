"""卡组结构和候选卡价值评估。"""

from __future__ import annotations

from collections import Counter


def _value(card, name: str, default=0):
    if isinstance(card, dict):
        return card.get(name, default)
    return getattr(card, name if name != "id" else "card_id", default)


def card_roles(card) -> set[str]:
    """用结构化数值为主、文本为辅识别卡牌职责。"""
    roles: set[str] = set()
    card_type = str(_value(card, "type", _value(card, "card_type", ""))).upper()
    text = f"{_value(card, 'id', '')} {_value(card, 'name', '')} {_value(card, 'description', '')}".lower()
    if card_type == "ATTACK" or _value(card, "damage", 0) > 0:
        roles.add("damage")
    if _value(card, "block", 0) > 0:
        roles.add("block")
    if card_type == "POWER" or any(word in text for word in ("strength", "dexterity", "力量", "敏捷", "每回合")):
        roles.add("scaling")
    if any(word in text for word in ("draw ", "draws ", "抽", "抓")):
        roles.add("draw")
    if any(word in text for word in ("gain energy", "energy.", "能量")):
        roles.add("energy")
    if any(word in text for word in ("all enemies", "all enemy", "所有敌人", "全体敌人")):
        roles.add("aoe")
    if any(word in text for word in ("vulnerable", "weak", "poison", "易伤", "虚弱", "中毒")):
        roles.add("debuff")
    if card_type in {"STATUS", "CURSE"}:
        roles.add("burden")
    return roles


def analyze_deck(cards) -> dict:
    cards = list(cards)
    role_counts: Counter[str] = Counter()
    names: Counter[str] = Counter()
    costs: list[int] = []
    for card in cards:
        role_counts.update(card_roles(card))
        names[str(_value(card, "name", _value(card, "id", "?")))] += 1
        cost = int(_value(card, "cost", -1))
        if cost >= 0:
            costs.append(cost)
    total = len(cards)
    return {
        "size": total,
        "average_cost": round(sum(costs) / len(costs), 2) if costs else 0.0,
        "roles": dict(role_counts),
        "duplicates": {name: count for name, count in names.items() if count > 1},
        "needs": [
            role for role, minimum in (("damage", 0.30), ("block", 0.25), ("draw", 0.08), ("scaling", 0.05))
            if total and role_counts[role] / total < minimum
        ],
    }


def evaluate_card(card, profile: dict) -> dict:
    roles = card_roles(card)
    score = 0.0
    reasons: list[str] = []
    for role in roles:
        if role in profile.get("needs", []):
            score += 2.0
            reasons.append(f"fills {role} gap")
    rarity = str(_value(card, "rarity", "")).upper()
    score += {"RARE": 1.2, "UNCOMMON": 0.5}.get(rarity, 0.0)
    name = str(_value(card, "name", _value(card, "id", "?")))
    duplicate_count = profile.get("duplicates", {}).get(name, 0)
    if duplicate_count >= 2:
        score -= min(1.5, duplicate_count * 0.35)
        reasons.append("duplicate saturation")
    if "burden" in roles:
        score -= 5.0
        reasons.append("status or curse")
    if profile.get("size", 0) >= 30 and not roles.intersection({"draw", "scaling", "energy"}):
        score -= 0.8
        reasons.append("large deck penalty")
    return {"score": round(score, 2), "roles": sorted(roles), "reasons": reasons}
