"""Parse LLM responses into game actions."""

from __future__ import annotations

import re
from communication.protocol import Decision


class InvalidDecisionError(ValueError):
    """模型没有给出可验证动作时抛出，禁止默认执行游戏操作。"""


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
        raise InvalidDecisionError("LLM response is empty")

    stripped = response.strip()
    text = stripped.upper()

    # Handle JSON format
    if text.startswith("{"):
        try:
            import json
            data = json.loads(response)
            action_type = data.get("type", "")
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
            raise InvalidDecisionError(f"unsupported JSON action: {action_type!r}")
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            if isinstance(exc, InvalidDecisionError):
                raise
            raise InvalidDecisionError(f"invalid JSON decision: {exc}") from exc

    # 只解析最后一行，避免把推理正文中的示例误当成最终动作。
    last_line = next((line.strip().upper() for line in reversed(stripped.splitlines()) if line.strip()), "")

    # Handle PLAY format
    play_match = re.fullmatch(r'PLAY\s+(\d+)(?:\s+(\d+))?', last_line)
    if play_match:
        hand_idx = int(play_match.group(1))
        monster_idx = int(play_match.group(2)) if play_match.group(2) else 0
        return Decision.play_card(hand_idx, monster_idx)

    # Handle POTION format
    potion_match = re.fullmatch(r'POTION\s+(\d+)(?:\s+(\d+))?', last_line)
    if potion_match:
        slot = int(potion_match.group(1))
        target = int(potion_match.group(2)) if potion_match.group(2) else 0
        return Decision.use_potion(slot, target)

    # Handle END format
    if last_line == "END":
        return Decision.end_turn()

    raise InvalidDecisionError(f"unrecognized decision line: {last_line!r}")
