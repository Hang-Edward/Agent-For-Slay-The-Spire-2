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
        hits = monster.intent_hits if monster.intent_hits > 1 else ""
        dmg_detail = f" for {monster.intent_damage} damage"
        if hits:
            dmg_detail += f" ({monster.intent_hits} hits)"
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


def build_combat_prompt(state: GameState, strategy_instructions: str = "") -> str:
    """Build a complete prompt for the LLM to make a combat decision."""

    prompt_parts = []

    # System preamble
    prompt_parts.append("""You are an expert Slay the Spire AI. You are playing a combat round.
Your goal is to choose the optimal card to play, or end the turn.
Think step by step about the situation, then output your decision.

OUTPUT FORMAT (one line only):
- To play a card: PLAY <hand_index> <monster_index>
- To end your turn: END

Example: PLAY 0 0  (play hand card 0 on monster 0)
Example: END       (end the turn)

IMPORTANT: Only output the command. No other text.
""")

    # Strategy instructions from skills system
    if strategy_instructions:
        prompt_parts.append(f"\n## Strategy\n{strategy_instructions}\n")

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
            if pot:
                potion_info.append(f"{pot.get('name', '?')} (slot {pot.get('slot', 0)})")
        if potion_info:
            prompt_parts.append(f"- Potions: {', '.join(potion_info)}\n")

    # Monsters
    prompt_parts.append("\n## Monsters\n")
    for i, mon in enumerate(state.alive_monsters):
        prompt_parts.append(f"  [{i}] {mon.name} | HP: {mon.current_hp}/{mon.max_hp} | Block: {mon.block}")
        prompt_parts.append(f"       Intent: {describe_intent(mon)}")
        if mon.powers:
            prompt_parts.append(f"       Powers: {format_powers(mon.powers)}")
        prompt_parts.append("")

    # Hand
    prompt_parts.append("\n## Your Hand\n")
    playable_count = 0
    for i, card in enumerate(state.hand):
        playable = card.is_playable and card.cost <= state.player_energy
        if playable:
            playable_count += 1
        energy_str = f"{card.cost}" + (" (upgraded)" if card.upgrades > 0 else "")
        marker = " [AVAILABLE]" if playable else " [NOT ENOUGH ENERGY]" if card.cost > state.player_energy else ""
        effect = format_card_effect(card)
        prompt_parts.append(f"  [{i}] {card.name} | Cost: {energy_str} | Type: {card.card_type}{marker}")
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
    prompt_parts.append(f"Decide which card to play (PLAY <idx> <monster_idx>) or END the turn.")

    return "\n".join(prompt_parts)
