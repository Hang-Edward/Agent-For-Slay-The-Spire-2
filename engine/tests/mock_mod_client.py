"""Mock Mod Client for testing the AI pipeline without a running game.

Reads game state from JSON fixture files instead of HTTP calls.
Supports single-state and multi-step scenarios.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from state.game_state import GameState
from communication.protocol import Decision


class MockModClient:
    """Mock client that reads game state from JSON fixture files."""

    def __init__(self, fixture_path: str = ""):
        self.base_url = "mock://local"
        self.timeout = 5.0
        self.fixture_path = fixture_path
        self._state: Optional[GameState] = None
        self._raw_state: Optional[dict] = None
        self._decision_log: list[Decision] = []
        self._connected = True
        self._step = 0
        self._sequence: list[str] = []

    def load_fixture(self, path: str) -> bool:
        """Load a single fixture file."""
        if not os.path.exists(path):
            print(f"[Mock] Fixture not found: {path}")
            return False
        with open(path) as f:
            self._raw_state = json.load(f)
        self._state = GameState.from_json(self._raw_state)
        print(f"[Mock] Loaded fixture: {os.path.basename(path)} ({self._state.screen_type})")
        return True

    def load_sequence(self, paths: list[str]) -> bool:
        """Load a sequence of fixture files for multi-step scenarios."""
        self._sequence = [p for p in paths if os.path.exists(p)]
        self._step = 0
        if not self._sequence:
            print("[Mock] No valid fixture files in sequence")
            return False
        return self.load_fixture(self._sequence[0])

    def get_state(self) -> Optional[GameState]:
        return self._state

    def get_raw_state(self) -> Optional[dict]:
        """Return the raw JSON dict for handlers that need screen-specific data."""
        return self._raw_state

    def post_decision(self, decision: Decision) -> bool:
        """Log a decision and advance to the next fixture if in sequence mode."""
        self._decision_log.append(decision)
        print(f"[Mock] Decision #{len(self._decision_log)}: {decision}")

        # In sequence mode, advance to next fixture
        if self._sequence and self._step + 1 < len(self._sequence):
            self._step += 1
            self.load_fixture(self._sequence[self._step])

        return True

    def get_status(self) -> dict:
        if not self._state:
            return {"in_battle": False, "awaiting_decision": False, "in_game": False}
        return {
            "in_battle": self._state.in_combat,
            "awaiting_decision": True,
            "in_game": True,
        }

    def is_connected(self) -> bool:
        return self._connected

    def get_decision_log(self) -> list[Decision]:
        """Return all decisions made during this mock session."""
        return self._decision_log

    @classmethod
    def from_fixture_dir(cls, fixture_dir: str) -> "MockModClient":
        """Create a client that iterates over all combat fixtures in a directory."""
        client = cls()
        fixtures = sorted(
            os.path.join(fixture_dir, f)
            for f in os.listdir(fixture_dir)
            if f.endswith(".json")
        )
        if fixtures:
            client.load_sequence(fixtures)
        return client
