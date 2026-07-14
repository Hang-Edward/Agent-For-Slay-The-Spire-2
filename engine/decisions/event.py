"""事件决策处理器 — 处理 EVENT 屏幕的选项选择。"""

from __future__ import annotations

import re

from .base import DecisionHandler
from communication.protocol import Decision


class EventHandler(DecisionHandler):
    """事件决策处理器。"""

    @property
    def screen_type(self) -> str:
        return "EVENT"

    def extract_state(self, raw_state: dict) -> dict:
        event_data = raw_state.get("event", {})
        player = raw_state.get("player", {})

        return {
            "event_name": event_data.get("name", "Unknown Event"),
            "event_body": event_data.get("body", ""),
            "options": event_data.get("options", []),
            "player_hp": player.get("current_hp", 0),
            "player_max_hp": player.get("max_hp", 0),
            "gold": player.get("gold", 0),
            "player_class": raw_state.get("class", "IRONCLAD"),
            "act": raw_state.get("act", 1),
            "floor": raw_state.get("floor", 1),
        }

    def build_prompt(self, state_data: dict, strategy_instructions: str = "") -> str:
        lines = []
        lines.append("You encounter an event in Slay the Spire. Choose the best option.")
        lines.append("")
        lines.append("Think step by step:")
        lines.append("1. Read the event description carefully.")
        lines.append("2. Consider each option: what does it cost (HP, gold) and what do you gain?")
        lines.append("3. Check your current state: can you afford the cost?")
        lines.append("4. Choose the option that best helps your run.")
        lines.append("")
        if strategy_instructions:
            lines.append("## Strategy Guidance")
            lines.append(strategy_instructions)
            lines.append("")
        lines.append(f"=== {state_data['event_name']} ===")
        lines.append(f"{state_data['event_body']}")
        lines.append("")
        lines.append(f"HP: {state_data['player_hp']}/{state_data['player_max_hp']} | Gold: {state_data['gold']}")
        lines.append(f"{state_data['player_class']} | Act {state_data['act']} Floor {state_data['floor']}")
        lines.append("")

        lines.append("## Options")
        for opt in state_data["options"]:
            idx = opt.get("index", 0)
            text = opt.get("text", "?")
            label = opt.get("label", "")
            lines.append(f"  [{idx}] {text}")
            if label:
                lines.append(f"       ({label})")
            lines.append("")

        lines.append("## Available Actions")
        lines.append("  CHOOSE <index> — Select an option")
        lines.append("")
        lines.append("Consider the risks and rewards given your current state.")
        lines.append("Output: CHOOSE <index>")

        return "\n".join(lines)

    def parse_response(self, llm_response: str, state_data: dict) -> Decision:
        text = llm_response.strip().upper()

        # JSON 格式
        if text.startswith("{"):
            try:
                import json
                data = json.loads(llm_response)
                action = data.get("type", "")
                if action == "choose_option":
                    idx = int(data.get("option_index", 0))
                    if 0 <= idx < len(state_data["options"]):
                        return Decision.choose_option(idx)
                    return Decision.choose_option(0)
            except Exception:
                pass

        # CHOOSE <index>
        choose_match = re.search(r'CHOOSE\s+(\d+)', text)
        if choose_match:
            idx = int(choose_match.group(1))
            if 0 <= idx < len(state_data["options"]):
                return Decision.choose_option(idx)
            return Decision.choose_option(0)

        # 默认选第一个选项
        return Decision.choose_option(0)
