"""Structured card database providing enriched card info for LLM prompts."""

from __future__ import annotations

import json
import os
from typing import Optional


class CardDatabase:
    """Structured card database that enriches LLM prompts beyond rawDescription."""

    _instance: Optional[CardDatabase] = None

    def __init__(self, data_dir: Optional[str] = None):
        self._cards: dict[str, dict] = {}
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__))
        self._load_all(data_dir)

    def _load_all(self, data_dir: str):
        """Load all *cards.json files from the data directory."""
        if not os.path.isdir(data_dir):
            return
        for fname in sorted(os.listdir(data_dir)):
            if fname.endswith("_cards.json"):
                path = os.path.join(data_dir, fname)
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    cards = data.get("cards", {})
                    self._cards.update(cards)
                except Exception:
                    pass

    def get_card_info(self, card_id: str) -> Optional[dict]:
        return self._cards.get(card_id)

    def get_description(self, card_id: str, upgraded: bool = False) -> str:
        info = self.get_card_info(card_id)
        if not info:
            return ""
        if upgraded and "upgrade_description" in info:
            return info["upgrade_description"]
        return info.get("description", "")

    def get_tags(self, card_id: str) -> list[str]:
        info = self.get_card_info(card_id)
        return info.get("tags", []) if info else []

    def get_synergy(self, card_id: str) -> list[str]:
        info = self.get_card_info(card_id)
        return info.get("synergy", []) if info else []

    def format_card_for_prompt(self, card_id: str, upgraded: bool = False) -> str:
        info = self.get_card_info(card_id)
        if not info:
            return ""

        parts = [f"{info.get('name', card_id)} ({info.get('rarity', '?')})"]
        parts.append(f"Cost: {info.get('cost', '?')}")

        if upgraded:
            desc = info.get("upgrade_description", info.get("description", ""))
        else:
            desc = info.get("description", "")

        parts.append(f"Effect: {desc}")

        tags = info.get("tags", [])
        if tags:
            parts.append(f"Tags: {', '.join(tag.replace('_', ' ') for tag in tags)}")

        synergy = info.get("synergy", [])
        if synergy:
            parts.append(f"Synergy: {', '.join(synergy)}")

        note = info.get("note", "")
        if note:
            parts.append(f"Tip: {note}")

        return " | ".join(parts)

    @classmethod
    def get_default(cls) -> CardDatabase:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
