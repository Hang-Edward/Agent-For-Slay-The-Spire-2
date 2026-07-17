from __future__ import annotations


def normalized_candidates(screen_type: str, state_data: dict) -> list[dict]:
    candidates = []
    if screen_type == "COMBAT":
        for item in state_data.get("turn_plan", {}).get("candidate_sequences", []):
            cards = item.get("cards", [])
            candidates.append({**item, "action_key": "cards:" + ",".join(map(str, cards)),
                               "score": float(item.get("score", 0))})
        return candidates
    route = {int(x["option_index"]): x for x in state_data.get("route_scores", [])}
    cards = {int(k): v for k, v in state_data.get("card_evaluations", {}).items()}
    for option in state_data.get("options", []):
        if not option.get("enabled", True) or "index" not in option:
            continue
        index = int(option["index"])
        detail = route.get(index, cards.get(index, {}))
        candidates.append({**detail, "option_index": index, "action_key": f"choice:{index}",
                           "score": float(detail.get("score", 0))})
    return candidates


def format_experience_evidence(candidates: list[dict], limit: int = 5) -> str:
    rows = [item for item in candidates if int(item.get("sample_count", 0)) > 0][:limit]
    if not rows:
        return ""
    lines = ["Historical experience evidence (advisory; current legal state wins):"]
    for item in rows:
        lines.append(f"- {item['action_key']}: baseline={item['baseline_score']}, "
                     f"history={item['historical_adjustment']:+.3f}, final={item['final_score']}, "
                     f"samples={item['sample_count']}, confidence={item['confidence']:.3f}")
    return "\n".join(lines)


def explain_decision(screen_type: str, state_data: dict, candidate: dict | None, source: str) -> str:
    if not candidate:
        return f"{source.upper()} 选择了当前唯一或安全动作。"
    parts = [f"{source.upper()} 选择 {candidate.get('action_key', 'action')}",
             f"评分 {candidate.get('final_score', candidate.get('score', 0))}"]
    if "estimated_hp_loss" in candidate:
        parts.append(f"预计承伤 {candidate['estimated_hp_loss']}")
    if candidate.get("reasons"):
        parts.append("卡组原因：" + "、".join(candidate["reasons"]))
    if candidate.get("sample_count", 0):
        parts.append(f"参考 {candidate['sample_count']} 条历史经验")
    return "；".join(parts) + "。"
