"""卡牌奖励决策处理器 — 处理 CARD_REWARD / BOSS_REWARD 屏幕的选牌决策。"""

from __future__ import annotations

from .base import DecisionHandler
from communication.protocol import Decision


class CardRewardHandler(DecisionHandler):
    """卡牌奖励选择处理器。"""

    @property
    def screen_type(self) -> str:
        return "CARD_REWARD"

    def can_handle(self, screen_type: str, raw_state: dict) -> bool:
        return screen_type in ("CARD_REWARD", "BOSS_REWARD")

    def extract_state(self, raw_state: dict) -> dict:
        rewards = raw_state.get("rewards", {})
        cards = rewards.get("cards", [])
        player = raw_state.get("player", {})
        discard = raw_state.get("discard_pile", [])

        # 统计现有卡组信息供 LLM 参考
        deck_cards = {}
        for c in discard:
            name = c.get("name", c.get("id", "?"))
            deck_cards[name] = deck_cards.get(name, 0) + 1

        # 统计费用曲线
        cost_curve = {}
        for c in discard:
            cost = c.get("cost", -1)
            if cost >= 0:
                cost_curve[cost] = cost_curve.get(cost, 0) + 1

        return {
            "cards": cards,
            "can_skip": rewards.get("can_skip", True),
            "player_hp": player.get("current_hp", 0),
            "player_max_hp": player.get("max_hp", 0),
            "player_class": raw_state.get("class", "IRONCLAD"),
            "act": raw_state.get("act", 1),
            "floor": raw_state.get("floor", 1),
            "gold": player.get("gold", 0),
            "deck_summary": deck_cards,
            "cost_curve": cost_curve,
            "total_cards": sum(deck_cards.values()),
        }

    def build_prompt(self, state_data: dict, strategy_instructions: str = "") -> str:
        lines = []
        lines.append("You are an expert Slay the Spire AI. Choose a card to add to your deck.")
        lines.append("")
        lines.append("Think step by step:")
        lines.append("1. Review your current deck: what's missing — damage, block, or scaling?")
        lines.append("2. Look at each reward card: how does it fit your deck?")
        lines.append("3. Consider the act and floor: what challenges are coming?")
        lines.append("4. Pick the card that improves your deck the most, or skip if none help.")
        lines.append("")
        if strategy_instructions:
            lines.append("## Strategy Guidance")
            lines.append(strategy_instructions)
            lines.append("")
        lines.append(f"You are playing {state_data['player_class']}, Act {state_data['act']} Floor {state_data['floor']}.")
        lines.append(f"HP: {state_data['player_hp']}/{state_data['player_max_hp']} | Gold: {state_data['gold']}")
        lines.append(f"Current deck size: {state_data['total_cards']} cards")
        lines.append("")

        if state_data["cost_curve"]:
            lines.append("## Current Deck Cost Curve")
            for cost in sorted(state_data["cost_curve"]):
                count = state_data["cost_curve"][cost]
                bar = "█" * min(count, 20)
                label = f"{cost} energy" if cost == 1 else f"{cost} energy"
                lines.append(f"  [{cost}] {bar} ({count})")
            lines.append("")

        # 列出候选卡牌
        lines.append("## Reward Cards")
        for i, card in enumerate(state_data["cards"]):
            name = card.get("name", "Unknown")
            rarity = card.get("rarity", "COMMON")
            card_type = card.get("type", "")
            cost = card.get("cost", "?")
            desc = card.get("description", "")
            upgrade_desc = card.get("upgrade_description", "")

            rarity_tag = {"COMMON": "", "UNCOMMON": "[Uncommon]", "RARE": "[RARE!]"}.get(rarity, "")

            lines.append(f"  [{i}] {name} {rarity_tag}")
            lines.append(f"       Cost: {cost} | Type: {card_type}")
            lines.append(f"       {desc}")
            if upgrade_desc:
                lines.append(f"       When upgraded: {upgrade_desc}")
            lines.append("")

        if state_data["can_skip"]:
            lines.append("## Available Actions")
            lines.append("  PICK <index> — Add the card to your deck")
            lines.append("  SKIP — Skip the reward")
        else:
            lines.append("## Available Actions")
            lines.append("  PICK <index> — Pick a card (can't skip)")

        lines.append("")
        lines.append("Consider your current deck composition and what would improve it.")
        lines.append("Output: PICK <index> or SKIP")

        return "\n".join(lines)

    def parse_response(self, llm_response: str, state_data: dict) -> Decision:
        text = llm_response.strip().upper()

        # JSON 格式
        if text.startswith("{"):
            try:
                import json
                data = json.loads(llm_response)
                action = data.get("type", "")
                if action == "pick_card":
                    idx = int(data.get("card_index", -1))
                    if idx >= 0 and idx < len(state_data["cards"]):
                        return Decision.pick_card(idx)
                    return Decision.skip_reward()
                elif action == "skip":
                    return Decision.skip_reward()
            except Exception:
                pass

        # 文本格式
        import re

        # SKIP
        if re.search(r'\bSKIP\b', text):
            return Decision.skip_reward()

        # PICK <index>
        pick_match = re.search(r'PICK\s+(\d+)', text)
        if pick_match:
            idx = int(pick_match.group(1))
            if 0 <= idx < len(state_data["cards"]):
                return Decision.pick_card(idx)

        # 默认跳过
        return Decision.skip_reward()
