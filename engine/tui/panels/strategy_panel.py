"""Strategy display panel for TUI."""

from __future__ import annotations

from rich.panel import Panel
from rich.text import Text


class StrategyPanel:
    """Displays current strategy settings."""

    def __init__(self):
        self.current_strategy = "balanced"
        self.active_skills: list[str] = []

    def update_strategy(self, name: str):
        self.current_strategy = name

    def update_skills(self, skills: list[str]):
        self.active_skills = skills

    def render(self) -> Panel:
        lines = [
            f"Strategy: [bold cyan]{self.current_strategy}[/]",
        ]
        if self.active_skills:
            lines.append(f"Skills: {', '.join(f'[green]{s}[/]' for s in self.active_skills)}")
        else:
            lines.append("Skills: [dim]none[/]")

        lines.append("[dim]Config: engine/config/ai_config.yaml[/]")

        return Panel("\n".join(lines), title="Strategy")
