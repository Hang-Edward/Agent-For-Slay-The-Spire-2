"""Terminal UI for real-time AI decision display."""

from __future__ import annotations

import threading
import time
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align

from ..state.game_state import GameState
from ..communication.protocol import Decision
from .panels.state_panel import StatePanel
from .panels.reasoning_panel import ReasoningPanel
from .panels.strategy_panel import StrategyPanel
from ..skills.model import SkillsRegistry


class TUIApp:
    """Terminal UI for the AI agent."""

    def __init__(self):
        self.console = Console()
        self.state_panel = StatePanel()
        self.reasoning_panel = ReasoningPanel()
        self.strategy_panel = StrategyPanel()
        self.layout = Layout()
        self._running = False
        self._live: Optional[Live] = None
        self._refresh_thread: Optional[threading.Thread] = None
        self.current_state: Optional[GameState] = None
        self.status_text = "Disconnected"
        self.connected = False
        self.pending_render = False

    def start(self):
        """Start the TUI display."""
        self._running = True
        self._build_layout()
        self._live = Live(self.layout, refresh_per_second=4, screen=True)
        self._live.__enter__()

    def stop(self):
        """Stop the TUI display."""
        self._running = False
        if self._live:
            try:
                self._live.__exit__(None, None, None)
            except Exception:
                pass
        self.console.print("[dim]TUI stopped.[/dim]")

    def _build_layout(self):
        """Build the layout structure."""
        self.layout.split_column(
            Layout(name="top", size=3),
            Layout(name="body"),
            Layout(name="bottom", size=3),
        )
        self.layout["body"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=3),
        )
        self.layout["bottom"].split_row(
            Layout(name="status", ratio=1),
            Layout(name="command", ratio=1),
        )

    def update_state(self, state: Optional[GameState]):
        """Update the current game state and refresh display."""
        self.current_state = state
        self.state_panel.update(state)

    def update_reasoning(self, text: str):
        """Update the reasoning panel."""
        self.reasoning_panel.update(text)

    def add_decision(self, llm_response: str, decision: Decision, elapsed_ms: int):
        """Add a decision record to the trace panel."""
        self.reasoning_panel.add_decision(llm_response, decision, elapsed_ms)

    def set_status(self, text: str, connected: bool = False):
        """Update the status bar."""
        self.status_text = text
        self.connected = connected

    def refresh(self):
        """Refresh the display with current data."""
        if not self._live:
            return

        # Header
        header_text = Text(" Slay the Spire — AI Agent ", style="bold white on blue")
        header = Panel(Align.center(header_text), style="blue")
        self.layout["top"].update(header)

        # Left panel: game state
        self.layout["left"].update(self.state_panel.render())

        # Right panel: reasoning
        self.layout["right"].update(self.reasoning_panel.render())

        # Status bar
        status_style = "green" if self.connected else "red"
        status = Panel(
            Text(f" {self.status_text}", style=status_style),
            style=status_style,
        )
        self.layout["status"].update(status)

        # Strategy panel (compact)
        self.layout["command"].update(self.strategy_panel.render())
