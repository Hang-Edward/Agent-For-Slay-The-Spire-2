#!/usr/bin/env python3
"""
Slay the Spire AI Agent — Main Entry Point

Connects to the Godot/.NET Mod via HTTP (or runs in --mock mode),
dispatches decisions based on screen type (combat, card reward, rest, event),
and displays everything in a real-time TUI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import time

from communication.mod_client import ModClient
from communication.protocol import Decision
from llm.base import LLMRequestError
from llm.factory import create_llm_client
from llm.response_parser import InvalidDecisionError
from decisions.registry import get_default_registry, DecisionRegistry
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
        model: str = "",
        config_path: str = "",
        backend: str = "deepseek",
        mock: bool = False,
        mock_file: str = "",
        dry_run: bool = False,
    ):
        # ── 客户端 ──────────────────────────────────────────
        self._mock_mode = mock
        self._dry_run = dry_run
        if mock:
            from tests.mock_mod_client import MockModClient
            self.client = MockModClient()
            if mock_file:
                self.client.load_fixture(mock_file)
        else:
            self.client = ModClient(mod_host, mod_port)

        # ── LLM ─────────────────────────────────────────────
        try:
            self.llm = create_llm_client(
                backend=backend,
                api_key=api_key,
                model=model,
                dry_run=dry_run,
            )
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

        # ── 决策处理器 ──────────────────────────────────────
        self.registry: DecisionRegistry = get_default_registry()

        # ── TUI ─────────────────────────────────────────────
        self.tui = TUIApp()

        # ── Skills ──────────────────────────────────────────
        self.skills_registry = SkillsRegistry()
        if config_path and os.path.exists(config_path):
            try:
                self.skills_registry = load_skills_from_config(config_path)
            except Exception as e:
                print(f"Warning: Failed to load config: {e}")

        # ── 追踪 ────────────────────────────────────────────
        self.trace_logger = TraceLogger()

        # ── 状态追踪 ────────────────────────────────────────
        self.running = False
        self.current_state_raw: dict | None = None
        self.last_screen_id: str = ""       # 用于避免重复决策
        self.mock_file_list: list[str] = []  # mock 多文件模式

    # ─── 公共接口 ───────────────────────────────────────────

    def start(self):
        """启动 AI Agent 主循环。"""
        if not self.llm.is_configured():
            print(f"ERROR: {self.llm.name} is not configured.")
            print("Check your API key or backend settings.")
            sys.exit(1)

        self.running = True
        self.tui.start()

        # 初始化连接状态
        if self._mock_mode:
            connected = True
            self.tui.set_status(f"Mock mode ({self.llm.name})", connected=True)
        else:
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

    def stop(self):
        """停止 AI Agent。"""
        self.running = False

    # ─── 主循环 ─────────────────────────────────────────────

    def _main_loop(self):
        """主循环：轮询游戏状态，根据屏幕类型分派决策。"""
        while self.running:
            # 获取状态
            state = self.client.get_state()
            if state is None:
                time.sleep(0.2)
                continue

            self.current_state_raw = state.raw if hasattr(state, 'raw') else {}
            self.tui.update_state(state)

            # 根据屏幕类型找到对应的决策处理器
            handler = self.registry.get_handler_for_state(self.current_state_raw)
            if handler is not None:
                state_data = handler.extract_state(self.current_state_raw)
                screen_id = self._compute_screen_id(
                    handler.screen_type, state_data
                )

                # 如果屏幕状态发生变化，需要做新决策
                if screen_id != self.last_screen_id and handler.should_act(state_data):
                    self._make_decision(state, handler, state_data)
                    self.last_screen_id = screen_id

            # 更新 TUI 状态栏
            screen = self.current_state_raw.get("screen_type", "?")
            in_combat = self.current_state_raw.get("in_combat", False)
            turn = state.turn if hasattr(state, 'turn') else 0
            act = state.act if hasattr(state, 'act') else 1
            floor = state.floor if hasattr(state, 'floor') else 1

            mode_name = self.llm.name
            status = (
                f"[{screen}] {mode_name}"
                f" | {'Turn ' + str(turn) if in_combat else ''}"
                f" | Act {act} Floor {floor}"
            )
            self.tui.set_status(status, connected=True)
            self.tui.refresh()

            time.sleep(0.3)

    # ─── 决策 ───────────────────────────────────────────────

    def _make_decision(self, state, handler, state_data):
        """执行一次决策：构建 Prompt → 调用 LLM → 解析 → 执行。"""
        start_time = time.time()

        # 获取 Skills 策略指令
        strategy_instructions = self.skills_registry.get_enabled_instructions()
        enabled_skill_names = [s.name for s in self.skills_registry.enabled_skills]

        # 构建 Prompt
        prompt = handler.build_prompt(state_data, strategy_instructions)
        self.tui.update_reasoning(f"{handler.screen_type}: Calling LLM...")

        # 追踪记录
        step = DecisionStep(
            turn=getattr(state, 'turn', 0),
            prompt=prompt,
            llm_response="",
            decision=Decision.end_turn(),
            reasoning="Thinking...",
        )

        # 尝试自动决策（跳过 LLM）
        auto_decision = handler.try_auto_decision(state_data)
        if auto_decision is not None:
            response = auto_decision.to_llm_format()
            elapsed_ms = 0
            decision = auto_decision
            reasoning = f"[auto] {response}"
            self.tui.update_reasoning(reasoning)
            self.tui.add_decision(response, decision, 0)
            self.tui.refresh()
            step.llm_response = response
            step.decision = decision
            step.elapsed_ms = 0
            self.trace_logger.add_step(step)
            print(f"\n[{handler.screen_type}] Auto: {decision}")
            if not self.client.post_decision(decision):
                self.tui.update_reasoning("Action rejected by mod; waiting for a new state")
            return

        # 调用 LLM
        try:
            response, elapsed = self.llm.think(prompt)
            elapsed_ms = int(elapsed * 1000)

            # 解析并校验响应；异常时本次状态不执行任何动作。
            decision = handler.parse_response(response, state_data)
        except (LLMRequestError, InvalidDecisionError) as error:
            message = f"[{handler.screen_type}] Decision stopped: {error}"
            self.tui.update_reasoning(message)
            self.tui.refresh()
            step.reasoning = message
            step.llm_response = locals().get("response", "")
            self.trace_logger.add_step(step)
            print(f"\n{message}")
            return

        # 更新 TUI
        reasoning = f"[{handler.screen_type}] LLM ({elapsed_ms}ms): {response[:100]}"
        self.tui.update_reasoning(reasoning)
        self.tui.add_decision(response, decision, elapsed_ms)
        self.tui.refresh()

        # 记录追踪
        step.llm_response = response
        step.decision = decision
        step.elapsed_ms = elapsed_ms
        self.trace_logger.add_step(step)

        print(f"\n[{handler.screen_type}] LLM: {response.strip()} → {decision} ({elapsed_ms}ms)")

        # 发送决策
        if not self.client.post_decision(decision):
            self.tui.update_reasoning("Action rejected by mod; waiting for a new state")

    # ─── 辅助方法 ───────────────────────────────────────────

    def _compute_screen_id(self, screen_type: str, state_data: dict) -> str:
        """为当前屏幕生成唯一 ID，用于判断是否需要新决策。"""
        # 战斗屏幕：基于手牌和怪物状态计算
        if screen_type == "COMBAT":
            gs = state_data.get("game_state")
            if gs:
                if gs.state_revision > 0:
                    return f"combat:{gs.state_revision}"
                raw = (
                    f"{gs.turn}|"
                    f"{'|'.join(f'{c.uuid}:{c.cost_for_turn}:{c.is_playable}' for c in gs.hand)}|"
                    f"{'|'.join(f'{m.monster_id}:{m.current_hp}:{m.block}' for m in gs.monsters)}|"
                    f"{gs.player_block}|{gs.player_energy}"
                )
                return hashlib.md5(raw.encode()).hexdigest()

        # 其他屏幕：基于状态数据的简单哈希
        raw = json.dumps(state_data, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()


# ─── Entry Point ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Slay the Spire AI Agent")
    parser.add_argument("--host", default="127.0.0.1", help="Mod HTTP server host")
    parser.add_argument("--port", type=int, default=18888, help="Mod HTTP server port")
    parser.add_argument("--api-key", default="", help="API key for the LLM backend")
    parser.add_argument("--model", default="", help="Model name override")
    parser.add_argument("--backend", default="", help="LLM backend: deepseek, ollama, claude")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "..", "config", "ai_config.yaml"),
        help="Path to config file",
    )
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no game required)")
    parser.add_argument("--mock-file", default="", help="Specific fixture file for mock mode")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode: simulate LLM with fixed responses (no API key needed)")

    args = parser.parse_args()

    # 从 YAML 加载配置（CLI args 覆盖 YAML）
    backend = args.backend
    model = args.model
    api_key = args.api_key

    config_path = args.config
    if not args.mock and os.path.exists(config_path):
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            llm_cfg = cfg.get("llm", {})
            if not backend:
                backend = llm_cfg.get("backend", "deepseek")
            if not model:
                model = llm_cfg.get("model", "")
            if not api_key:
                api_key = llm_cfg.get("api_key", "")
        except Exception:
            pass

    # 尝试从 api_key.yaml 读取 API key（fallback）
    if not api_key and not args.mock and not args.dry_run:
        api_key_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config", "api_key.yaml"
        )
        if os.path.exists(api_key_path):
            try:
                import yaml
                with open(api_key_path) as f:
                    key_cfg = yaml.safe_load(f)
                if key_cfg and "llm" in key_cfg:
                    api_key = key_cfg["llm"].get("api_key", "")
            except Exception:
                pass

    # 最后尝试环境变量
    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    if not backend:
        backend = "deepseek"

    agent = AIAgent(
        mod_host=args.host,
        mod_port=args.port,
        api_key=api_key,
        model=model,
        config_path=args.config if not args.mock else "",
        backend=backend,
        mock=args.mock,
        mock_file=args.mock_file,
        dry_run=args.dry_run,
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
