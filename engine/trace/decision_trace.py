"""Decision tracing data model."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from state.game_state import GameState, Card, Monster
from communication.protocol import Decision


@dataclass
class DecisionStep:
    """Record of a single decision step."""
    turn: int
    prompt: str
    llm_response: str
    decision: Decision
    reasoning: str = ""
    elapsed_ms: int = 0
    state_snapshot: str = ""


@dataclass
class BattleTrace:
    """Full trace of a battle."""
    character: str = ""
    ascension: int = 0
    act: int = 1
    steps: list[DecisionStep] = field(default_factory=list)
    monsters_encountered: list[str] = field(default_factory=list)
    won: Optional[bool] = None

    def add_step(self, step: DecisionStep):
        self.steps.append(step)

    def summary(self) -> str:
        return (f"Battle | {len(self.steps)} decisions | "
                f"Monsters: {', '.join(self.monsters_encountered[-3:])}")
