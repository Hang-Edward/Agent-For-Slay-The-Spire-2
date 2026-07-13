"""Parse LLM responses into game actions."""

from __future__ import annotations

import re
from ..communication.protocol import Decision


def parse_llm_response(response: str) -> Decision:
    """Parse an LLM response into a Decision object.

    Accepted formats:
      PLAY <hand_index> [monster_index]
      END
      POTION <slot> [target]

    Also accepts JSON:
      {"type": "play_card", "hand_index": 0, "monster_index": 0}
    """
    if not response:
        return Decision.end_turn()

    text = response.strip().upper()

    # Handle JSON format
    if text.startswith("{"):
        try:
            import json
            data = json.loads(response)
            action_type = data.get("type", "end_turn")
            if action_type == "end_turn":
                return Decision.end_turn()
            elif action_type == "play_card":
                hi = int(data.get("hand_index", 0))
                mi = int(data.get("monster_index", 0))
                return Decision.play_card(hi, mi)
            elif action_type == "use_potion":
                slot = int(data.get("potion_slot", 0))
                target = int(data.get("monster_index", 0))
                return Decision.use_potion(slot, target)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # Handle PLAY format
    play_match = re.search(r'PLAY\s+(\d+)(?:\s+(\d+))?', text)
    if play_match:
        hand_idx = int(play_match.group(1))
        monster_idx = int(play_match.group(2)) if play_match.group(2) else 0
        return Decision.play_card(hand_idx, monster_idx)

    # Handle POTION format
    potion_match = re.search(r'POTION\s+(\d+)(?:\s+(\d+))?', text)
    if potion_match:
        slot = int(potion_match.group(1))
        target = int(potion_match.group(2)) if potion_match.group(2) else 0
        return Decision.use_potion(slot, target)

    # Handle END format
    if re.search(r'\bEND\b', text):
        return Decision.end_turn()

    # Try to find anything that looks like a decision
    for token in text.split():
        if token == "END":
            return Decision.end_turn()

    # Default: end turn
    return Decision.end_turn()
