"""Game state display panel for TUI."""

from __future__ import annotations

from typing import Optional

from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout

from ...state.game_state import GameState


class StatePanel:
    """Displays the current game state."""

    def __init__(self):
        self.state: Optional[GameState] = None

    def update(self, state: Optional[GameState]):
        self.state = state

    def render(self) -> Panel:
        if not self.state:
            return Panel("Waiting for game...", title="Game State")

        s = self.state
        layout = Layout()
        layout.split_column(
            Layout(name="player", size=8),
            Layout(name="monsters"),
        )

        # Player info
        player_info = Table.grid(padding=(0, 1))
        player_info.add_column("Label", style="bold")
        player_info.add_column("Value")

        hp_color = "green" if s.player_hp > s.player_max_hp * 0.5 else "yellow" if s.player_hp > s.player_max_hp * 0.3 else "red"
        player_info.add_row("HP", f"[{hp_color}]{s.player_hp}/{s.player_max_hp}[/]")
        player_info.add_row("Block", f"[cyan]{s.player_block}[/]")
        player_info.add_row("Energy", f"[yellow]{s.player_energy}/{s.player_energy_this_turn}[/]")

        if s.player_powers:
            powers = ", ".join(
                f"{p.get('name', p.get('id', '?'))}[dim]({p.get('amount', 0)})[/]"
                for p in s.player_powers
            )
            player_info.add_row("Powers", powers)

        if s.relics:
            relics = ", ".join(r.get("name", r.get("id", "?")) for r in s.relics[:5])
            player_info.add_row("Relics", f"[dim]{relics}[/]")

        if s.potions:
            pots = ", ".join(
                p.get("name", "?") for p in s.potions if p
            )
            player_info.add_row("Potions", f"[magenta]{pots}[/]")

        player_info.add_row("Deck", f"Draw: {s.draw_pile_count} | Discard: {len(s.discard_pile)} | Exhaust: {len(s.exhaust_pile)}")
        player_info.add_row("Turn", f"{s.turn} | Act {s.act} Floor {s.floor}")

        layout["player"].update(Panel(player_info, title=f"Player ({s.char_class})"))

        # Monster table
        monster_table = Table(show_header=True, header_style="bold red")
        monster_table.add_column("#", width=3)
        monster_table.add_column("Monster")
        monster_table.add_column("HP", width=10)
        monster_table.add_column("Block", width=5)
        monster_table.add_column("Intent", width=20)
        monster_table.add_column("Dmg", width=4)
        monster_table.add_column("Powers")

        for i, m in enumerate(s.alive_monsters):
            hp_str = f"[red]{m.current_hp}[/]/[dim]{m.max_hp}[/]"
            if m.current_hp <= 0:
                hp_str = "[dim]DEAD[/]"

            intent_color = {
                "ATTACK": "red",
                "ATTACK_BUFF": "red",
                "ATTACK_DEBUFF": "red",
                "BUFF": "yellow",
                "DEBUFF": "magenta",
                "DEFEND": "cyan",
            }.get(m.intent, "white")

            intent_str = m.intent
            if m.intent_damage > 0:
                hits = f"x{m.intent_hits}" if m.intent_hits > 1 else ""
                intent_str += f" [{intent_color}]{m.intent_damage}{hits}[/]"

            powers = ", ".join(
                f"{p.get('name', p.get('id', '?'))}({p.get('amount', 0)})"
                for p in m.powers
            ) if m.powers else ""

            monster_table.add_row(
                str(i),
                m.name,
                hp_str,
                str(m.block),
                f"[{intent_color}]{intent_str}[/]",
                str(m.intent_damage) if m.intent_damage > 0 else "-",
                f"[dim]{powers}[/]",
            )

        # Hand info
        if s.hand:
            hand_text = []
            for i, c in enumerate(s.hand):
                cost_color = "yellow" if c.cost <= s.player_energy else "red"
                marker = " ✓" if c.is_playable and c.cost <= s.player_energy else ""
                hand_text.append(
                    f"  [{i}] [bold]{c.name}[/] [yellow]({c.cost})[/]{marker}"
                )
            monster_panel = Panel(
                "\n".join(hand_text),
                title=f"Hand ({len(s.hand)} cards)",
                border_style="blue",
            )
            layout["monsters"].split_column(
                Layout(Panel(monster_table, title=f"Monsters ({len(s.alive_monsters)})"), size=8),
                Layout(monster_panel),
            )
        else:
            layout["monsters"].update(Panel(monster_table, title=f"Monsters ({len(s.alive_monsters)})"))

        return Panel(layout, title="Game State")
