"""HTTP client for communicating with the Slay the Spire Mod."""

from __future__ import annotations

import requests
from typing import Optional
from ..state.game_state import GameState
from .protocol import Decision


class ModClient:
    """Client for the Slay the Spire AI Mod HTTP API."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18888, timeout: float = 5.0):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.session = requests.Session()

    def get_state(self) -> Optional[GameState]:
        """Fetch the current game state from the mod."""
        try:
            resp = self.session.get(
                f"{self.base_url}/state",
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if "error" in data:
                return None
            return GameState.from_json(data)
        except (requests.ConnectionError, requests.Timeout, ValueError):
            return None

    def post_decision(self, decision: Decision) -> bool:
        """Send an AI decision to the mod."""
        try:
            resp = self.session.post(
                f"{self.base_url}/decision",
                json=decision.to_json(),
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except (requests.ConnectionError, requests.Timeout):
            return False

    def get_status(self) -> dict:
        """Get mod status."""
        try:
            resp = self.session.get(
                f"{self.base_url}/status",
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.json()
        except (requests.ConnectionError, requests.Timeout):
            pass
        return {"in_battle": False, "awaiting_decision": False, "in_game": False}

    def is_connected(self) -> bool:
        """Check if the mod is reachable."""
        try:
            resp = self.session.get(
                f"{self.base_url}/status",
                timeout=2.0,
            )
            return resp.status_code == 200
        except (requests.ConnectionError, requests.Timeout):
            return False
