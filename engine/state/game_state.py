"""Data models for Slay the Spire game state."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Card:
    """A card in the game."""
    uuid: str
    card_id: str
    name: str
    cost: int
    cost_for_turn: int
    card_type: str  # ATTACK, SKILL, POWER, CURSE, STATUS
    rarity: str
    target_type: str
    has_target: bool
    is_playable: bool
    playable_reason: str
    upgrades: int
    damage: int
    block: int
    magic_number: int
    exhausts: bool
    ethereal: bool
    description: str = ""

    @classmethod
    def from_json(cls, data: dict) -> "Card":
        return cls(
            uuid=data.get("uuid", ""),
            card_id=data.get("id", ""),
            name=data.get("name", ""),
            cost=data.get("cost", 0),
            cost_for_turn=data.get("cost_for_turn", data.get("cost", 0)),
            card_type=data.get("type", "ATTACK"),
            rarity=data.get("rarity", "COMMON"),
            target_type=data.get("target_type", ""),
            has_target=data.get("has_target", False),
            is_playable=data.get("is_playable", True),
            playable_reason=data.get("playable_reason", ""),
            upgrades=data.get("upgrades", 0),
            damage=data.get("damage", 0),
            block=data.get("block", 0),
            magic_number=data.get("magic_number", 0),
            exhausts=data.get("exhausts", False),
            ethereal=data.get("ethereal", False),
            description=data.get("description", ""),
        )


@dataclass
class Monster:
    """A monster in combat."""
    monster_id: str
    name: str
    current_hp: int
    max_hp: int
    block: int
    intent: str  # ATTACK, BUFF, DEBUFF, etc.
    intent_damage: int
    intent_hits: int
    is_gone: bool
    half_dead: bool
    targetable: bool
    target_index: int
    powers: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict) -> "Monster":
        return cls(
            monster_id=data.get("id", ""),
            name=data.get("name", ""),
            current_hp=data.get("current_hp", 0),
            max_hp=data.get("max_hp", 1),
            block=data.get("block", 0),
            intent=data.get("intent", "NONE"),
            intent_damage=data.get("intent_damage", 0),
            intent_hits=data.get("intent_hits", 1),
            is_gone=data.get("is_gone", False),
            half_dead=data.get("half_dead", False),
            targetable=data.get("targetable", not data.get("is_gone", False)),
            target_index=data.get("target_index", -1),
            powers=data.get("powers", []),
        )

    @property
    def is_alive(self) -> bool:
        return not self.is_gone and self.current_hp > 0

    @property
    def is_attacking(self) -> bool:
        return "ATTACK" in self.intent


@dataclass
class GameState:
    """Complete game state."""
    screen_type: str
    in_combat: bool
    player_hp: int
    player_max_hp: int
    player_block: int
    player_energy: int
    player_energy_this_turn: int
    player_powers: list[dict]
    monsters: list[Monster]
    hand: list[Card]
    draw_pile_count: int
    discard_pile: list[Card]
    exhaust_pile: list[Card]
    relics: list[dict]
    potions: list[dict]
    turn: int
    act: int
    floor: int
    ascension_level: int
    char_class: str
    decision_ready: bool = True
    action_in_flight: bool = False
    action_in_progress: bool = False
    state_revision: int = 0
    gold: int = 0
    raw: dict = field(default_factory=dict)  # original JSON

    @property
    def alive_monsters(self) -> list[Monster]:
        return [m for m in self.monsters if m.is_alive]

    @property
    def targetable_monsters(self) -> list[Monster]:
        return [m for m in self.alive_monsters if m.targetable]

    @property
    def total_monster_hp(self) -> int:
        return sum(m.current_hp for m in self.alive_monsters)

    def get_playable_cards(self) -> list[tuple[int, Card]]:
        return [(i, c) for i, c in enumerate(self.hand) if c.is_playable]

    @classmethod
    def from_json(cls, data: dict) -> "GameState":
        return cls(
            screen_type=data.get("screen_type", ""),
            in_combat=data.get("in_combat", False),
            player_hp=data.get("player", {}).get("current_hp", 0),
            player_max_hp=data.get("player", {}).get("max_hp", 0),
            player_block=data.get("player", {}).get("block", 0),
            player_energy=data.get("player", {}).get("energy", 0),
            player_energy_this_turn=data.get("player", {}).get("energy_this_turn", 0),
            player_powers=data.get("player", {}).get("powers", []),
            monsters=[Monster.from_json(m) for m in data.get("monsters", [])],
            hand=[Card.from_json(c) for c in data.get("hand", [])],
            draw_pile_count=data.get("draw_pile_count", 0),
            discard_pile=[Card.from_json(c) for c in data.get("discard_pile", [])],
            exhaust_pile=[Card.from_json(c) for c in data.get("exhaust_pile", [])],
            relics=data.get("relics", []),
            potions=data.get("potions", []),
            turn=data.get("turn", 0),
            act=data.get("act", 1),
            floor=data.get("floor", 1),
            ascension_level=data.get("ascension_level", 0),
            char_class=data.get("class", "IRONCLAD"),
            decision_ready=data.get("decision_ready", True),
            action_in_flight=data.get("action_in_flight", False),
            action_in_progress=data.get("action_in_progress", False),
            state_revision=data.get("state_revision", 0),
            gold=data.get("player", {}).get("gold", 0),
            raw=data,
        )
