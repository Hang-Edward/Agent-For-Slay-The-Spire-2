#!/usr/bin/env python3
"""
Slay the Spire AI Agent — Main Entry Point

Connects to the Java Mod via HTTP,
calls DeepSeek V4 Flash for decisions,
and displays everything in a real-time TUI.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import signal
import threading

from communication.mod_client import ModClient
from llm.prompt_builder import build_combat_prompt
from llm.deepseek_client import DeepSeekClient
from llm.response_parser import parse_llm_response
from communication.protocol import Decision
from state.game_state import GameState
from skills.model import SkillsRegistry
from skills.loader import load_skills_from_config
from trace.decision_trace import DecisionStep
from trace.trace_logger import TraceLogger
from tui.app import TUIApp


class AIAgent:
    """Main AI agent that orchestrates everything."""

    def __init__(
        self,
        mod_host: str = "127.0.0.1",
        mod_port: int = 18888,
        api_key: str = "",
        model: str = "deepseek-chat",
        config_path: str = "",
    ):
        self.client = ModClient(mod_host, mod_port)
        self.llm = DeepSeekClient(api_key, model)
        self.tui = TUIApp()

        # Load skills
        self.skills_registry = SkillsRegistry()
        if config_path and os.path.exists(config_path):
            try:
                self.skills_registry = load_skills_from_config(config_path)
            except Exception as e:
                print(f"Warning: Failed to load config: {e}")

        self.trace_logger = TraceLogger()
        self.last_turn = -1
        self.last_state_hash = ""
        self.running = False
        self.in_combat = False
        self.current_state: GameState | None = None

    def start(self):
        """Start the AI agent main loop."""
        if not self.llm.is_configured():
            print("ERROR: DeepSeek API key not configured.")
            print("Set DEEPSEEK_API_KEY environment variable or pass --api-key")
            sys.exit(1)

        self.running = True
        self.tui.start()

        # Quick connection status display
        connected = self.client.is_connected()
        self.tui.set_status(
            f"{'Connected' if connected else 'Disconnected — waiting for mod...'} "
            f"({self.client.base_url})",
            connected=connected,
        )

        try:
            self._main_loop()
        except KeyboardInterrupt:
            pass
        finally:
            self.tui.stop()

    def _main_loop(self):
        """Main loop: poll mod state, make decisions when needed."""
        while self.running:
            # Check mod connection
            status = self.client.get_status()
            connected = status.get("in_game", False)

            if not connected:
                self.tui.set_status("Waiting for game/mod connection...", False)
                self.tui.refresh()
                time.sleep(1)
                continue

            self.tui.set_status("Connected — monitoring combat...", True)

            # Get full state
            state = self.client.get_state()
            if state is None:
                time.sleep(0.2)
                continue

            self.current_state = state
            self.tui.update_state(state)

            # Check if we're in active combat needing a decision
            if self._should_make_decision(state):
                self._make_decision(state)

            # Update TUI
            self.tui.set_status(
                f"Connected — {'In combat (turn ' + str(state.turn) + ')' if state.in_combat else 'Exploring'} "
                f"| Act {state.act} Floor {state.floor}",
                connected=True,
            )
            self.tui.refresh()

            # Throttle polling
            time.sleep(0.3)

    def _should_make_decision(self, state: GameState) -> bool:
        """Check if the AI needs to make a decision."""
        if not state.in_combat:
            self.in_combat = False
            return False

        if not state.hand:
            return False

        # Don't act on dead monsters / empty battle
        if not state.alive_monsters:
            return False

        # Check if turn changed - new turn needs new decisions
        if state.turn != self.last_turn:
            self.last_turn = state.turn
            self.last_state_hash = ""
            return True

        # Check if hand state changed (card was played, drew new cards)
        state_hash = self._hash_state(state)
        if state_hash != self.last_state_hash and any(c.is_playable and c.cost <= state.player_energy for c in state.hand):
            self.last_state_hash = state_hash
            return True

        return False

    def _hash_state(self, state: GameState) -> str:
        """Create a hash to detect meaningful state changes."""
        hand_info = "|".join(f"{c.uuid}:{c.cost}:{c.is_playable}" for c in state.hand)
        monster_info = "|".join(f"{m.monster_id}:{m.current_hp}:{m.block}" for m in state.monsters)
        return f"{hand_info}||{monster_info}||{state.player_block}||{state.player_energy}"

    def _make_decision(self, state: GameState):
        """Make a combat decision using the LLM."""
        start_time = time.time()

        # Get skill instructions
        strategy_instructions = self.skills_registry.get_enabled_instructions()
        enabled_skill_names = [s.name for s in self.skills_registry.enabled_skills]

        # Build prompt
        prompt = build_combat_prompt(state, strategy_instructions)
        self.tui.update_reasoning("Calling DeepSeek API...")

        # Show prompt in trace
        step = DecisionStep(
            turn=state.turn,
            prompt=prompt,
            llm_response="",
            decision=Decision.end_turn(),
            reasoning="Thinking...",
        )

        # Call LLM
        response, elapsed = self.llm.think(prompt)
        elapsed_ms = int(elapsed * 1000)

        # Parse response
        decision = parse_llm_response(response)

        # Show reasoning in TUI
        reasoning = f"LLM responded in {elapsed_ms}ms: {response[:100]}"
        self.tui.update_reasoning(reasoning)
        self.tui.add_decision(response, decision, elapsed_ms)
        self.tui.refresh()

        # Record trace
        step.llm_response = response
        step.decision = decision
        step.elapsed_ms = elapsed_ms
        self.trace_logger.add_step(step)

        print(f"\n[Turn {state.turn}] LLM: {response.strip()} → Decision: {decision} ({elapsed_ms}ms)")

        # Send decision
        if decision.type == "end_turn":
            self.client.post_decision(decision)
            self.last_turn = state.turn  # Don't re-act on same turn after end
        else:
            # For card plays, send and wait for state change
            self.client.post_decision(decision)
            self.last_state_hash = ""  # Force re-evaluation after action

    def stop(self):
        """Stop the AI agent."""
        self.running = False


def main():
    parser = argparse.ArgumentParser(description="Slay the Spire AI Agent")
    parser.add_argument("--host", default="127.0.0.1", help="Mod HTTP server host")
    parser.add_argument("--port", type=int, default=18888, help="Mod HTTP server port")
    parser.add_argument("--api-key", default="", help="DeepSeek API key")
    parser.add_argument("--model", default="deepseek-chat", help="DeepSeek model name")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "..", "config", "ai_config.yaml"),
        help="Path to config file",
    )

    args = parser.parse_args()

    # API key priority: CLI arg > env var
    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY", "")

    agent = AIAgent(
        mod_host=args.host,
        mod_port=args.port,
        api_key=api_key,
        model=args.model,
        config_path=args.config,
    )

    def signal_handler(sig, frame):
        print("\nShutting down...")
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    agent.start()


if __name__ == "__main__":
    main()
