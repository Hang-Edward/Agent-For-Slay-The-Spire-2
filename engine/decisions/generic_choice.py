"""通用非战斗选择处理器，覆盖地图、奖励、商店、事件和选牌界面。"""

from __future__ import annotations

import json
import re
from collections import Counter

from communication.protocol import Decision
from llm.response_parser import InvalidDecisionError
from strategy.deck_evaluator import analyze_deck, evaluate_card
from strategy.route_planner import score_map_options
from .base import DecisionHandler


class GenericChoiceHandler(DecisionHandler):
    """处理 Mod 暴露的统一 ``options`` 协议。"""

    @property
    def screen_type(self) -> str:
        return "CHOICE"

    def can_handle(self, screen_type: str, raw_state: dict) -> bool:
        return screen_type != "COMBAT" and isinstance(raw_state.get("options"), list)

    def extract_state(self, raw_state: dict) -> dict:
        deck = raw_state.get("deck", [])
        options = raw_state.get("options", [])
        player = raw_state.get("player", {})
        deck_profile = analyze_deck(deck)
        return {
            "screen_type": raw_state.get("screen_type", "CHOICE"),
            "room_type": raw_state.get("room_type", ""),
            "decision_ready": raw_state.get("decision_ready", False),
            "options": options,
            "player": player,
            "deck": deck,
            "deck_profile": deck_profile,
            "card_evaluations": {
                int(option["index"]): evaluate_card(option["card"], deck_profile)
                for option in options if option.get("card") and "index" in option
            },
            "route_scores": score_map_options(
                raw_state.get("map", {}), options,
                player.get("current_hp", 0), player.get("max_hp", 0), player.get("gold", 0),
            ),
            "relics": raw_state.get("relics", []),
            "potions": raw_state.get("potions", []),
            "act": raw_state.get("act", 0),
            "floor": raw_state.get("floor", 0),
            "class": raw_state.get("class", ""),
        }

    def build_prompt(self, state_data: dict, strategy_instructions: str = "") -> str:
        player = state_data["player"]
        lines = [
            "You are controlling a complete Slay the Spire 2 run through a text API.",
            "Choose exactly one currently available option. Consider long-term run value, survival, deck synergy, and path risk.",
            "",
            f"Screen: {state_data['screen_type']} | Room: {state_data['room_type']}",
            f"Character: {state_data['class']} | Act {state_data['act']} Floor {state_data['floor']}",
            f"HP: {player.get('current_hp', 0)}/{player.get('max_hp', 0)} | Gold: {player.get('gold', 0)}",
        ]

        if strategy_instructions:
            lines.extend(["", "Strategy guidance:", strategy_instructions])

        deck_counts = Counter(card.get("name", card.get("id", "?")) for card in state_data["deck"])
        if deck_counts:
            lines.extend(["", "Deck:", ", ".join(f"{name} x{count}" for name, count in deck_counts.items())])
            profile = state_data["deck_profile"]
            lines.append(
                f"Deck profile: size={profile['size']}, average_cost={profile['average_cost']}, "
                f"roles={profile['roles']}, current_gaps={profile['needs']}"
            )

        if state_data["route_scores"]:
            lines.extend(["", "Full-map route analysis (higher score balances rewards, HP risk, and gold):"])
            for route in state_data["route_scores"]:
                lines.append(
                    f"  option {route['option_index']}: score={route['score']}, "
                    f"best_path_rooms={route['best_path_counts']}, alternatives={route['path_count']}"
                )

        relic_names = [relic.get("name", relic.get("id", "?")) for relic in state_data["relics"]]
        if relic_names:
            lines.extend(["", "Relics: " + ", ".join(relic_names)])

        potion_names = [potion.get("name", potion.get("id", "?")) for potion in state_data["potions"]]
        if potion_names:
            lines.append("Potions: " + ", ".join(potion_names))

        lines.extend(["", "Available options:"])
        stalled = set(state_data.get("stalled_option_indices", []))
        enabled_indices = {
            int(option["index"])
            for option in state_data["options"]
            if option.get("enabled", True) and "index" in option
        }
        has_untried = bool(enabled_indices - stalled)
        for option in state_data["options"]:
            index = int(option.get("index", -1))
            if not option.get("enabled", True):
                status = "DISABLED"
            elif option.get("selected", False):
                status = "SELECTED"
            elif has_untried and index in stalled:
                status = "STALLED_PREVIOUSLY"
            else:
                status = "AVAILABLE"
            cost = option.get("cost", -1)
            cost_text = f" | cost={cost}" if isinstance(cost, int) and cost >= 0 else ""
            coord = ""
            if option.get("row", -1) >= 0:
                coord = f" | map=({option['row']},{option.get('column', -1)})"
            lines.append(
                f"[{option.get('index')}] [{status}] {option.get('kind', 'choice')}: "
                f"{option.get('name', option.get('id', '?'))}{cost_text}{coord}"
            )
            description = option.get("description", "")
            if description:
                lines.append(f"    {description}")
            for model_key in ("card", "relic", "potion"):
                model = option.get(model_key)
                if model:
                    lines.append(f"    {model_key}: {json.dumps(model, ensure_ascii=False)}")
            evaluation = state_data["card_evaluations"].get(int(option.get("index", -1)))
            if evaluation:
                lines.append(
                    f"    deck fit: score={evaluation['score']}, roles={evaluation['roles']}, "
                    f"reasons={evaluation['reasons']}"
                )

        lines.extend([
            "",
            "Prefer an AVAILABLE option over STALLED_PREVIOUSLY; the latter already failed to change the game state.",
            "Return exactly one final line and no extra action:",
            "CHOOSE <index>",
        ])
        return "\n".join(lines)

    def parse_response(self, llm_response: str, state_data: dict) -> Decision:
        if not llm_response:
            raise InvalidDecisionError("LLM response is empty")

        stripped = llm_response.strip()
        index: int | None = None
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                if data.get("type") != "choose_option":
                    raise InvalidDecisionError("JSON action must be choose_option")
                index = int(data["option_index"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, InvalidDecisionError):
                    raise
                raise InvalidDecisionError(f"invalid choice JSON: {exc}") from exc
        else:
            last_line = next((line.strip() for line in reversed(stripped.splitlines()) if line.strip()), "")
            match = re.fullmatch(r"CHOOSE\s+(\d+)", last_line, re.IGNORECASE)
            if not match:
                raise InvalidDecisionError(f"unrecognized choice line: {last_line!r}")
            index = int(match.group(1))

        valid = {
            int(option["index"])
            for option in state_data["options"]
            if option.get("enabled", True) and "index" in option
        }
        if index not in valid:
            raise InvalidDecisionError(f"choice index is unavailable: {index}; valid={sorted(valid)}")
        return Decision.choose_option(index)

    def should_act(self, state_data: dict) -> bool:
        return bool(state_data.get("decision_ready")) and any(
            option.get("enabled", True) for option in state_data.get("options", [])
        )

    def try_auto_decision(self, state_data: dict) -> Decision | None:
        enabled = [option for option in state_data["options"] if option.get("enabled", True)]
        # 卡牌选择已产生选中项且确认按钮可用时，继续选牌只会造成界面空转。
        if state_data.get("screen_type", "").startswith("CARD_SELECT"):
            has_selected_card = any(
                option.get("kind") == "card" and option.get("selected", False)
                for option in enabled
            )
            confirm = next((option for option in enabled if option.get("kind") == "confirm"), None)
            if has_selected_card and confirm is not None:
                return Decision.choose_option(int(confirm["index"]))
        if len(enabled) == 1:
            return Decision.choose_option(int(enabled[0]["index"]))
        return None

    def fallback_decision(self, state_data: dict) -> Decision | None:
        """模型失败时选择一个未卡住的合法选项，并保留已有策略评分。"""
        enabled = [
            option for option in state_data["options"]
            if option.get("enabled", True) and "index" in option
        ]
        if not enabled:
            return None

        automatic = self.try_auto_decision(state_data)
        if automatic is not None:
            return automatic

        stalled = set(state_data.get("stalled_option_indices", []))
        candidates = [option for option in enabled if int(option["index"]) not in stalled] or enabled

        route_scores = {
            int(route["option_index"]): float(route["score"])
            for route in state_data.get("route_scores", [])
        }
        route_candidates = [option for option in candidates if int(option["index"]) in route_scores]
        if route_candidates:
            selected = max(route_candidates, key=lambda option: route_scores[int(option["index"])])
            return Decision.choose_option(int(selected["index"]))

        card_scores = {
            int(index): float(evaluation["score"])
            for index, evaluation in state_data.get("card_evaluations", {}).items()
        }
        card_candidates = [option for option in candidates if int(option["index"]) in card_scores]
        if card_candidates:
            selected = max(card_candidates, key=lambda option: card_scores[int(option["index"])])
            return Decision.choose_option(int(selected["index"]))

        return Decision.choose_option(int(candidates[0]["index"]))
