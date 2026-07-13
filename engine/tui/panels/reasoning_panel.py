"""AI reasoning display panel for TUI."""

from __future__ import annotations

from typing import Optional
from collections import deque

from rich.panel import Panel
from rich.text import Text
from rich.console import Group
from rich.table import Table
from rich.layout import Layout

from ...communication.protocol import Decision


class ReasoningPanel:
    """Displays the AI's reasoning process."""

    def __init__(self, max_history: int = 20):
        self.current_reasoning = "Waiting..."
        self.history: deque[dict] = deque(maxlen=max_history)

    def update(self, text: str):
        self.current_reasoning = text

    def add_decision(self, llm_response: str, decision: Decision, elapsed_ms: int):
        self.history.append({
            "llm_response": llm_response,
            "decision": str(decision),
            "elapsed_ms": elapsed_ms,
        })

    def render(self) -> Panel:
        layout = Layout()
        layout.split_column(
            Layout(name="current", size=12),
            Layout(name="history"),
        )

        # Current reasoning
        reasoning_text = Text(self.current_reasoning)
        current_panel = Panel(
            reasoning_text,
            title="AI Thinking",
            border_style="green",
        )
        layout["current"].update(current_panel)

        # Decision history
        if self.history:
            table = Table(show_header=True, header_style="bold dim")
            table.add_column("#", width=3)
            table.add_column("Decision", width=16)
            table.add_column("Response excerpt", width=50)
            table.add_column("Time")

            for i, entry in enumerate(reversed(list(self.history)[-8:])):
                response = entry["llm_response"][:40] + "..." if len(entry["llm_response"]) > 40 else entry["llm_response"]
                table.add_row(
                    str(len(self.history) - i),
                    f"[cyan]{entry['decision']}[/]",
                    f"[dim]{response}[/]",
                    f"{entry['elapsed_ms']}ms",
                )

            history_panel = Panel(
                table,
                title="Decision History",
                border_style="dim",
            )
        else:
            history_panel = Panel(
                Text("No decisions yet", style="dim"),
                title="Decision History",
                border_style="dim",
            )

        layout["history"].update(history_panel)
        return Panel(layout, title="AI Reasoning")
