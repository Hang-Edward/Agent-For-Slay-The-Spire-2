"""Builds prompts for the LLM from game state."""

from __future__ import annotations
from typing import Optional
from state.game_state import GameState, Monster, Card


# Intent descriptions to help the LLM understand enemy behavior
INTENT_DESCRIPTIONS = {
    "ATTACK": "will attack this turn",
    "ATTACK_BUFF": "will attack and gain a buff",
    "ATTACK_DEBUFF": "will attack and apply a debuff",
    "BUFF": "will gain a buff",
    "DEBUFF": "will apply a debuff",
    "DEFEND": "will gain block",
    "DEFEND_DEBUFF": "will block and debuff",
    "DEFEND_BUFF": "will block and buff",
    "ESCAPE": "will attempt to escape",
    "SLEEP": "is asleep",
    "STUN": "is stunned",
    "NONE": "has no intent (neutral)",
    "DEBUG": "unknown behavior",
}

# Monster intent damage descriptions
def describe_intent(monster: Monster) -> str:
    base = INTENT_DESCRIPTIONS.get(monster.intent, "has unknown intent")
    if monster.intent_damage > 0:
        dmg_detail = f" for {monster.intent_damage} damage"
        if monster.intent_hits > 1:
            total = monster.intent_damage * monster.intent_hits
            dmg_detail += f" x {monster.intent_hits} hits ({total} total)"
        base += dmg_detail
    if monster.block > 0:
        base += f" with {monster.block} block"
    return base


def format_powers(powers: list[dict]) -> str:
    """Format power/buff list into a readable string."""
    if not powers:
        return "none"
    return ", ".join(f"{p.get('name', p.get('id', '?'))} ({p.get('amount', 0)})" for p in powers)


def format_card_effect(card: Card) -> str:
    """Build a concise effect description from card data."""
    parts = []
    if card.card_type == "ATTACK" and card.damage > 0:
        dmg = card.damage
        if card.upgrades > 0:
            dmg = card.damage  # already updated value
        parts.append(f"Deal {dmg} damage")
    if card.card_type == "SKILL" and card.block > 0:
        parts.append(f"Gain {card.block} block")
    if card.magic_number > 0:
        if card.card_id in ("Flex", "Inflame", "Limit Break", "Spot Weakness"):
            parts.append(f"Gain {card.magic_number} Strength")
        elif card.card_id in ("Bludgeon", "Immolate", "Whirlwind"):
            pass  # damage already covered
        else:
            parts.append(f"Magic: {card.magic_number}")
    if card.exhausts:
        parts.append("(Exhausts)")
    if card.ethereal:
        parts.append("(Ethereal)")
    if parts:
        return " | ".join(parts)
    return card.description or "unknown effect"


def build_combat_prompt(state: GameState, strategy_instructions: str = "", turn_plan: dict | None = None) -> str:
    """Build a complete prompt for the LLM to make a combat decision."""

    prompt_parts = []

    # System preamble
    prompt_parts.append("""You are an expert Slay the Spire AI. Choose the optimal next action.

Use the supplied whole-turn analysis, HP budget, current state, and strategy guidance to evaluate the whole remaining turn. The state will be refreshed and replanned after every card.

Return exactly ONE command and no explanation, reasoning, markdown, or punctuation:
PLAY <hand_index> <monster_index>
POTION <slot> <monster_index>
END
""")

    # Strategy instructions from skills system
    if strategy_instructions:
        prompt_parts.append(f"\n## Strategy\n{strategy_instructions}\n")

    if turn_plan:
        prompt_parts.append("\n## Whole-turn risk budget")
        prompt_parts.append(
            f"Incoming={turn_plan['incoming_damage']} | currently unblocked={turn_plan['unblocked_damage']} "
            f"| risk={turn_plan['risk']} | acceptable HP loss={turn_plan['acceptable_hp_loss']}"
        )
        prompt_parts.append("Top feasible sequences (static estimates; card effects may require replanning):")
        for sequence in turn_plan.get("candidate_sequences", [])[:6]:
            prompt_parts.append(
                f"  cards={sequence['cards']} {sequence['names']} | energy={sequence['cost']} "
                f"| damage={sequence['damage']} | block={sequence['block']} "
                f"| damage_avoided_by_kills={sequence['damage_avoided_by_kills']} "
                f"| estimated_hp_loss={sequence['estimated_hp_loss']}"
            )

    # Player status
    prompt_parts.append(f"""## Player Status
- HP: {state.player_hp}/{state.player_max_hp}
- Block: {state.player_block}
- Energy: {state.player_energy}/{state.player_energy_this_turn} (available this turn)
- Powers: {format_powers(state.player_powers)}
""")

    # Relics (show only the names to keep prompt size manageable)
    if state.relics:
        relic_names = ", ".join(r.get("name", r.get("id", "?")) for r in state.relics)
        prompt_parts.append(f"- Relics: {relic_names}\n")

    # Potions
    if state.potions:
        potion_info = []
        for pot in state.potions:
            if pot and pot.get("can_use", False):
                target = pot.get("target_type", "")
                description = pot.get("description", "")
                detail = f", effect: {description}" if description else ""
                potion_info.append(f"{pot.get('name', '?')} (slot {pot.get('slot', 0)}, target: {target}{detail})")
        if potion_info:
            prompt_parts.append(f"- Potions: {', '.join(potion_info)}\n")

    if state.teammates:
        prompt_parts.append("\n## Teammates")
        for mate in state.teammates:
            prompt_parts.append(
                f"- {mate.character} ({mate.net_id}): HP {mate.current_hp}/{mate.max_hp}, "
                f"block {mate.block}, energy {mate.energy}, hand {mate.hand_count}, phase {mate.phase}"
            )
        teammate_actions = [action for action in state.team_actions if not action.get("is_local", False)]
        if teammate_actions:
            prompt_parts.append("Teammate actions this turn:")
            for action in teammate_actions[-12:]:
                prompt_parts.append(f"  - {action.get('description', '?')}")
        prompt_parts.append(
            "Coordinate with the resulting state: avoid duplicate lethal damage and account for teammate debuffs or setup. "
            "Do not assume a teammate's personal block protects you."
        )

    local_actions = [action for action in state.team_actions if action.get("is_local", False)]
    if local_actions:
        prompt_parts.append("\n## Your actions already completed this turn")
        for action in local_actions[-12:]:
            prompt_parts.append(f"  - {action.get('description', '?')}")

    # Monsters
    prompt_parts.append("\n## Monsters\n")
    for fallback_index, mon in enumerate(state.alive_monsters):
        target_index = mon.target_index if mon.target_index >= 0 else fallback_index
        target_label = str(target_index) if mon.targetable else "not targetable"
        prompt_parts.append(f"  [{target_label}] {mon.name} | HP: {mon.current_hp}/{mon.max_hp} | Block: {mon.block}")
        prompt_parts.append(f"       Intent: {describe_intent(mon)}")
        if mon.powers:
            prompt_parts.append(f"       Powers: {format_powers(mon.powers)}")
        prompt_parts.append("")

    # Hand
    prompt_parts.append("\n## Your Hand\n")
    playable_count = 0
    for i, card in enumerate(state.hand):
        playable = card.is_playable and card.cost_for_turn <= state.player_energy
        if playable:
            playable_count += 1
        energy_str = f"{card.cost_for_turn}" + (" (upgraded)" if card.upgrades > 0 else "")
        marker = " [AVAILABLE]" if playable else f" [UNPLAYABLE: {card.playable_reason or 'unknown'}]"
        effect = format_card_effect(card)
        prompt_parts.append(f"  [{i}] {card.name} | Cost: {energy_str} | Type: {card.card_type}{marker}")
        if card.target_type:
            prompt_parts.append(f"       Target: {card.target_type}")
        prompt_parts.append(f"       Effect: {effect}")
        prompt_parts.append("")

    # Deck info
    prompt_parts.append(f"\n## Draw Pile: {state.draw_pile_count} cards remaining")
    prompt_parts.append(f"## Discard Pile: {len(state.discard_pile)} cards")
    if state.exhaust_pile:
        prompt_parts.append(f"## Exhaust Pile: {len(state.exhaust_pile)} cards")

    # Visible discard pile for context
    if state.discard_pile:
        disc_names = [c.name for c in state.discard_pile[-5:]]  # last 5
        prompt_parts.append(f"  Recent discards: {', '.join(disc_names)}")

    # Turn & game info
    prompt_parts.append(f"\n## Turn {state.turn} | Act {state.act} Floor {state.floor}")
    if state.ascension_level > 0:
        prompt_parts.append(f"## Ascension {state.ascension_level}")

    # Available actions summary
    prompt_parts.append(f"\n## Available Actions")
    prompt_parts.append(f"You have {state.player_energy} energy and {playable_count} playable cards.")
    prompt_parts.append(f"Decide which card to play (PLAY <idx> <monster_idx>), potion to use (POTION <slot> <monster_idx>), or END the turn.")

    return "\n".join(prompt_parts)
