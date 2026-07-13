"""Trace logger for recording AI decisions."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional
from .decision_trace import BattleTrace, DecisionStep


class TraceLogger:
    """Logs AI decision traces to files."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.current_trace: Optional[BattleTrace] = None
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def start_battle(self, character: str, ascension: int, act: int):
        self.current_trace = BattleTrace(
            character=character,
            ascension=ascension,
            act=act,
        )

    def add_step(self, step: DecisionStep):
        if self.current_trace:
            self.current_trace.add_step(step)

    def end_battle(self, won: bool):
        if self.current_trace:
            self.current_trace.won = won
            self._save_trace()
            self.current_trace = None

    def _save_trace(self):
        if not self.current_trace:
            return
        trace = self.current_trace
        filename = f"battle_{self.session_id}_{datetime.now().strftime('%H%M%S')}.json"
        filepath = os.path.join(self.log_dir, filename)

        data = {
            "character": trace.character,
            "ascension": trace.ascension,
            "act": trace.act,
            "won": trace.won,
            "steps": [
                {
                    "turn": s.turn,
                    "reasoning": s.reasoning,
                    "llm_response": s.llm_response,
                    "decision": str(s.decision),
                    "elapsed_ms": s.elapsed_ms,
                }
                for s in trace.steps
            ],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
