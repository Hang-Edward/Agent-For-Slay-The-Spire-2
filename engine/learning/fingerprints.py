from __future__ import annotations

import hashlib
import json


def state_features(context: dict) -> dict:
    player = context.get("player", {})
    max_hp = max(1, int(player.get("max_hp", 1)))
    return {
        "screen_type": context.get("screen_type", ""),
        "character": context.get("class", context.get("character", "")),
        "act": int(context.get("act", 0)),
        "hp_band": int(5 * int(player.get("current_hp", 0)) / max_hp),
        "enemy_key": ",".join(sorted(str(m.get("id", "")) for m in context.get("monsters", []))),
        "deck_key": ",".join(sorted(str(c.get("id", "")) for c in context.get("deck", []))),
    }


def state_fingerprint(context: dict) -> str:
    raw = json.dumps(state_features(context), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
