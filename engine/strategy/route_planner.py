"""完整地图 DAG 路线评分。"""

from __future__ import annotations

from collections import Counter


ROOM_ALIASES = {
    "MONSTER": "monster", "ELITE": "elite", "RESTSITE": "rest", "REST_SITE": "rest", "REST": "rest",
    "SHOP": "shop", "EVENT": "event", "UNKNOWN": "event", "TREASURE": "treasure",
    "BOSS": "boss", "ANCIENT": "ancient",
}


def _node_score(node_type: str, hp_ratio: float, gold: int) -> float:
    room = ROOM_ALIASES.get(node_type.upper(), node_type.lower())
    weights = {"monster": 1.6, "elite": 2.8, "event": 1.0, "rest": 0.4,
               "shop": 0.2, "treasure": 2.0, "ancient": 1.5, "boss": 0.0}
    score = weights.get(room, 0.0)
    if room == "elite":
        score += 1.5 if hp_ratio >= 0.70 else -3.5
    if room == "monster" and hp_ratio < 0.40:
        score -= 2.2
    if room in {"event", "rest"} and hp_ratio < 0.50:
        score += 1.8
    if room == "shop":
        score += 3.0 if gold >= 180 else (1.2 if gold >= 100 else -1.0)
    return score


def score_map_options(map_graph: dict, options: list[dict], hp: int, max_hp: int, gold: int) -> list[dict]:
    nodes = {node.get("id"): node for node in map_graph.get("nodes", [])}
    hp_ratio = hp / max(1, max_hp)

    def paths(start_id: str, seen: frozenset[str] = frozenset()) -> list[list[dict]]:
        if start_id in seen or start_id not in nodes:
            return []
        node = nodes[start_id]
        children = [child for child in node.get("children", []) if child in nodes]
        if not children:
            return [[node]]
        result: list[list[dict]] = []
        for child in children:
            result.extend([[node, *tail] for tail in paths(child, seen | {start_id})])
        return result[:256]

    scored: list[dict] = []
    for option in options:
        if option.get("kind") != "map" or not option.get("enabled", True):
            continue
        node_id = option.get("id", "")
        if node_id not in nodes:
            continue
        route_paths = paths(node_id) or [[nodes[node_id]]]
        path_results = []
        for path in route_paths:
            counts = Counter(ROOM_ALIASES.get(str(node.get("type", "")).upper(), str(node.get("type", "")).lower()) for node in path)
            score = sum(_node_score(str(node.get("type", "")), hp_ratio, gold) for node in path)
            path_results.append((score, counts, [node.get("id") for node in path]))
        if path_results:
            best_score, counts, node_path = max(path_results, key=lambda item: item[0])
            scored.append({
                "option_index": int(option["index"]),
                "score": round(best_score, 2),
                "best_path_counts": dict(counts),
                "best_path": node_path,
                "path_count": len(path_results),
            })
    return sorted(scored, key=lambda item: item["score"], reverse=True)
