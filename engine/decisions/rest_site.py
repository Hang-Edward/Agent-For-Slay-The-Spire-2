"""篝火决策处理器 — 处理 REST 屏幕的休息/锻造决策。"""

from __future__ import annotations

import re

from .base import DecisionHandler
from communication.protocol import Decision


class RestSiteHandler(DecisionHandler):
    """篝火决策处理器。"""

    @property
    def screen_type(self) -> str:
        return "REST"

    def extract_state(self, raw_state: dict) -> dict:
        rest_data = raw_state.get("rest_site", {})
        player = raw_state.get("player", {})
        discard = raw_state.get("discard_pile", [])

        # 统计所有可升级的卡牌
        upgradeable = []
        seen = set()
        for c in discard:
            cid = c.get("id", "")
            if cid and cid not in seen:
                seen.add(cid)
                upgradeable.append({
                    "index": len(upgradeable),
                    "card_id": cid,
                    "name": c.get("name", "?"),
                    "upgrades": c.get("upgrades", 0),
                })

        return {
            "has_rest": rest_data.get("has_rest", True),
            "has_smith": rest_data.get("has_smith", True),
            "heal_amount": rest_data.get("heal_amount", 0),
            "upgradeable_cards": upgradeable or rest_data.get("upgradeable_cards", []),
            "player_hp": player.get("current_hp", 0),
            "player_max_hp": player.get("max_hp", 0),
            "player_class": raw_state.get("class", "IRONCLAD"),
            "act": raw_state.get("act", 1),
            "floor": raw_state.get("floor", 1),
        }

    def build_prompt(self, state_data: dict, strategy_instructions: str = "") -> str:
        lines = []
        lines.append("You are at a rest site. Choose: REST to heal, or SMITH to upgrade a card.")
        lines.append("")
        lines.append("Think step by step:")
        lines.append("1. Check your HP: are you in danger of dying in the next fight?")
        lines.append("2. If HP is low, REST is safer.")
        lines.append("3. If HP is comfortable, consider SMITH on your most important card.")
        lines.append("4. Make your choice.")
        lines.append("")
        if strategy_instructions:
            lines.append("## Strategy Guidance")
            lines.append(strategy_instructions)
            lines.append("")
        lines.append(f"{state_data['player_class']} | Act {state_data['act']} Floor {state_data['floor']}")
        lines.append(f"HP: {state_data['player_hp']}/{state_data['player_max_hp']}")
        lines.append(f"Heal amount if resting: +{state_data['heal_amount']} HP")
        lines.append("")

        upgradeable = state_data.get("upgradeable_cards", [])
        if upgradeable and state_data["has_smith"]:
            lines.append("## Upgradeable Cards")
            for card in upgradeable:
                name = card.get("name", "?")
                upgrades = card.get("upgrades", 0)
                marker = " (already upgraded)" if upgrades > 0 else ""
                lines.append(f"  [{card['index']}] {name}{marker}")
            lines.append("")

        lines.append("## Available Actions")
        if state_data["has_rest"]:
            lines.append("  REST — Heal HP")
        if state_data["has_smith"] and upgradeable:
            lines.append("  SMITH <index> — Upgrade a card")
        lines.append("")
        lines.append("Consider: if your HP is low, REST is safer. If your deck needs power, SMITH.")
        lines.append("Output: REST or SMITH <index>")

        return "\n".join(lines)

    def parse_response(self, llm_response: str, state_data: dict) -> Decision:
        text = llm_response.strip().upper()

        # JSON 格式
        if text.startswith("{"):
            try:
                import json
                data = json.loads(llm_response)
                action = data.get("type", "")
                if action == "rest":
                    return Decision.rest()
                elif action == "smith":
                    return Decision.smith(int(data.get("card_index", 0)))
            except Exception:
                pass

        # SMITH <index>
        smith_match = re.search(r'SMITH\s+(\d+)', text)
        if smith_match:
            idx = int(smith_match.group(1))
            return Decision.smith(idx)

        # REST
        if re.search(r'\bREST\b', text):
            return Decision.rest()

        # 默认休息
        return Decision.rest()
