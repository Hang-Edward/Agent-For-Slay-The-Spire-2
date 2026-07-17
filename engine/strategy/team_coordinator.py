"""多人回合等待策略。"""

from __future__ import annotations

import time

from state.game_state import GameState


class TeamCoordinator:
    def __init__(self, enabled: bool = True, timeout_seconds: float = 20.0):
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self._turn_key: tuple[int, int] | None = None
        self._wait_started = 0.0

    def should_wait(self, state: GameState) -> tuple[bool, str]:
        active = [mate for mate in state.teammates if mate.is_alive and mate.phase.lower() == "play"]
        if not self.enabled or not active:
            self._turn_key = None
            return False, ""
        key = (state.act, state.turn)
        now = time.monotonic()
        if key != self._turn_key:
            self._turn_key = key
            self._wait_started = now
        elapsed = now - self._wait_started
        if elapsed >= self.timeout_seconds:
            return False, f"teammate wait timeout after {elapsed:.1f}s"
        names = ", ".join(mate.character or mate.net_id for mate in active)
        return True, f"waiting for teammates to finish: {names} ({elapsed:.1f}/{self.timeout_seconds:.0f}s)"
