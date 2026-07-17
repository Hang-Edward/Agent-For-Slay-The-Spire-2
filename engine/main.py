#!/usr/bin/env python3
"""
Slay the Spire AI Agent — Main Entry Point

Connects to the Godot/.NET Mod via HTTP (or runs in --mock mode),
dispatches decisions based on screen type (combat, card reward, rest, event),
and displays everything in a real-time TUI.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
import signal
import sys
import time
from uuid import uuid4

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
from strategy.team_coordinator import TeamCoordinator
from dashboard.server import DashboardServer
from explanation.decision_explainer import explain_decision, format_experience_evidence, normalized_candidates
from history.rewards import RewardCalculator
from history.run_store import RunHistoryStore
from learning.experience_service import ExperienceService
from learning.experience_store import ExperienceStore
from policy.local_policy import LocalPolicy
from teacher.deepseek_teacher import TeacherReviewService
from telemetry.event_bus import DecisionEventBus


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
        decision_mode: str = "llm",
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
        self.decision_mode = decision_mode
        self.policy = LocalPolicy()
        self.teacher_enabled = False
        self.teacher_review_on_run_end = True

        # ── 决策处理器 ──────────────────────────────────────
        self.registry: DecisionRegistry = get_default_registry()

        # ── TUI ─────────────────────────────────────────────
        self.tui = TUIApp()

        # ── Skills ──────────────────────────────────────────
        self.skills_registry = SkillsRegistry()
        self.team_coordinator = TeamCoordinator()
        if config_path and os.path.exists(config_path):
            try:
                self.skills_registry = load_skills_from_config(config_path)
                import yaml
                with open(config_path, encoding="utf-8") as config_file:
                    config_data = yaml.safe_load(config_file) or {}
                multiplayer = config_data.get("strategy", {}).get("multiplayer", {})
                self.team_coordinator = TeamCoordinator(
                    enabled=multiplayer.get("wait_for_teammates", True),
                    timeout_seconds=float(multiplayer.get("wait_timeout_seconds", 20)),
                )
                teacher_config = config_data.get("teacher", {})
                self.teacher_enabled = bool(teacher_config.get("enabled", False))
                self.teacher_review_on_run_end = bool(teacher_config.get("review_on_run_end", True))
            except Exception as e:
                print(f"Warning: Failed to load config: {e}")

        # ── 追踪 ────────────────────────────────────────────
        self.trace_logger = TraceLogger()

        # ── 实时面板、历史与经验学习 ────────────────────────
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(project_dir, "data")
        self.event_bus = DecisionEventBus(secret_values=(api_key,))
        self.history_store = RunHistoryStore(self.data_dir)
        self.event_bus.add_sink(self.history_store)
        self.reward_calculator = RewardCalculator()
        self.experience_store = ExperienceStore(os.path.join(self.data_dir, "experience.sqlite3"))
        self.experience_service = ExperienceService(self.experience_store)
        self.teacher = TeacherReviewService(self.llm, enabled=self.teacher_enabled)
        self.dashboard = DashboardServer(self.event_bus, self.history_store)
        self.current_run_id = ""
        self.current_battle_id = ""
        self.run_completed = False
        self.pending_transition: dict | None = None
        self.policy_version = "experience-v1"

        # ── 状态追踪 ────────────────────────────────────────
        self.running = False
        self.current_state_raw: dict | None = None
        self.last_screen_id: str = ""       # 用于避免重复决策
        self.next_decision_time: float = 0.0  # 失败后限速重试，避免永久卡住或高频请求
        self.last_action_time: float = 0.0
        self.last_decision: Decision | None = None
        self.stalled_options: dict[str, set[int]] = {}
        self.decision_failure_count: int = 0
        self.mock_file_list: list[str] = []  # mock 多文件模式

    # ─── 公共接口 ───────────────────────────────────────────

    def start(self):
        """启动 AI Agent 主循环。"""
        if not self.llm.is_configured():
            print(f"ERROR: {self.llm.name} is not configured.")
            print("Check your API key or backend settings.")
            sys.exit(1)

        self.running = True
        try:
            self.dashboard.start()
            print(f"Decision dashboard: {self.dashboard.url}")
            self._emit("dashboard_started", {"url": self.dashboard.url, "phase": "waiting_for_game"})
        except OSError as error:
            print(f"Dashboard unavailable; Agent will continue: {error}")
            self._emit("dashboard_error", {"message": str(error)})
        self.tui.start()

        # 初始化连接状态
        if self._mock_mode:
            connected = True
            self.tui.set_status(f"Mock mode ({self.llm.name})", connected=True)
        else:
            connected = self.client.is_connected()
            self.tui.set_status(
                f"{'Connected' if connected else 'Disconnected - waiting for mod...'} "
                f"({self.client.base_url})",
                connected=connected,
            )

        try:
            self._main_loop()
        except KeyboardInterrupt:
            pass
        finally:
            for closer in (self.dashboard.stop, self.history_store.close,
                           self.experience_store.close, self.tui.stop):
                try:
                    closer()
                except Exception as error:
                    print(f"Shutdown warning: {error}")

    def stop(self):
        """停止 AI Agent。"""
        self.running = False

    # ─── 主循环 ─────────────────────────────────────────────

    def _main_loop(self):
        """主循环：轮询游戏状态，根据屏幕类型分派决策。"""
        while self.running:
            try:
                self._run_iteration()
            except Exception as error:
                # 单个未知界面或瞬时解析错误不能终止无人值守进程。
                message = f"Agent iteration failed; retrying in 2s: {error}"
                print(f"\n{message}")
                self.tui.update_reasoning(message)
                self._emit("decision_error", {"message": str(error), "phase": "error"})
                self.tui.refresh()
                time.sleep(2.0)

    def _run_iteration(self):
        state = self.client.get_state()
        if state is None:
            time.sleep(0.2)
            return

        raw_state = state.raw if hasattr(state, "raw") else {}
        self._settle_pending_transition(raw_state)
        self.current_state_raw = raw_state
        self._ensure_run(raw_state)
        self._emit("state_received", {
            "phase": "reading_state",
            "snapshot_patch": {"game_state": raw_state},
        })
        self._complete_run_if_needed(raw_state)
        self.tui.update_state(state)

        handler = self.registry.get_handler_for_state(self.current_state_raw)
        if handler is not None:
            state_data = handler.extract_state(self.current_state_raw)
            screen_id = self._compute_screen_id(handler.screen_type, state_data)
            now = time.monotonic()
            waiting_for_team = False
            if handler.screen_type == "COMBAT":
                waiting_for_team, wait_reason = self.team_coordinator.should_wait(state_data["game_state"])
                if waiting_for_team:
                    self.tui.update_reasoning(wait_reason)
                    self._emit("waiting_for_team", {"reason": wait_reason, "phase": "waiting_for_team"})

            # Mod 的门闩会在 10 秒后释放无进展动作；Agent 随后必须允许同屏重试。
            stalled = (
                screen_id == self.last_screen_id
                and self.last_action_time > 0
                and now - self.last_action_time >= 12.0
                and self.current_state_raw.get("decision_ready", False)
                and not self.current_state_raw.get("action_in_flight", False)
            )
            if stalled:
                if self.last_decision and self.last_decision.type == "choose_option":
                    self.stalled_options.setdefault(screen_id, set()).add(
                        self.last_decision.option_index
                    )
                self.last_screen_id = ""
                self.next_decision_time = now
                self.tui.update_reasoning("No state progress after action; choosing again")

            avoided = self.stalled_options.get(screen_id, set())
            if avoided:
                state_data["stalled_option_indices"] = sorted(avoided)

            if (
                screen_id != self.last_screen_id
                and now >= self.next_decision_time
                and not waiting_for_team
                and handler.should_act(state_data)
            ):
                if self._make_decision(state, handler, state_data):
                    self.last_screen_id = screen_id
                    self.last_action_time = time.monotonic()
                    self.next_decision_time = 0.0
                    self.decision_failure_count = 0
                else:
                    self.decision_failure_count += 1
                    retry_delay = min(30.0, 2.0 ** min(self.decision_failure_count, 5))
                    self.next_decision_time = time.monotonic() + retry_delay

        screen = self.current_state_raw.get("screen_type", "?")
        in_combat = self.current_state_raw.get("in_combat", False)
        status = (
            f"[{screen}] {self.llm.name}"
            f" | {'Turn ' + str(state.turn) if in_combat else ''}"
            f" | Act {state.act} Floor {state.floor}"
        )
        self.tui.set_status(status, connected=True)
        self.tui.refresh()
        time.sleep(0.3)

    # ─── 决策 ───────────────────────────────────────────────

    def _make_decision(self, state, handler, state_data) -> bool:
        """执行一次决策：构建 Prompt → 调用 LLM → 解析 → 执行。"""
        strategy_instructions = self.skills_registry.get_enabled_instructions()
        candidates = normalized_candidates(handler.screen_type, state_data)
        current_state = getattr(self, "current_state_raw", {}) or {}
        experience_service = getattr(self, "experience_service", None)
        if experience_service is not None:
            adjusted = experience_service.apply(current_state, candidates)
        else:
            # 兼容绕过构造函数的轻量测试和诊断环境。
            adjusted = [
                {
                    **candidate,
                    "baseline_score": candidate.get("score", 0.0),
                    "historical_adjustment": 0.0,
                    "final_score": candidate.get("score", 0.0),
                    "sample_count": 0,
                    "confidence": 0.0,
                }
                for candidate in candidates
            ]
        evidence = format_experience_evidence(adjusted)
        combined = "\n".join(part for part in (strategy_instructions, evidence) if part)
        prompt = handler.build_prompt(state_data, combined)
        self._emit("candidates_scored", {
            "phase": "evaluating_candidates",
            "candidates": adjusted,
            "snapshot_patch": {"current_decision": {
                "screen_type": handler.screen_type, "status": "evaluating",
                "candidates": adjusted, "prompt": prompt,
            }},
        })
        self.tui.update_reasoning(f"{handler.screen_type}: Calling LLM...")
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
            reasoning = f"[auto] {response}"
            self.tui.update_reasoning(reasoning)
            self.tui.add_decision(response, auto_decision, 0)
            self.tui.refresh()
            step.llm_response = response
            step.decision = auto_decision
            step.elapsed_ms = 0
            self.trace_logger.add_step(step)
            print(f"\n[{handler.screen_type}] Auto: {auto_decision}")
            return self._submit_decision(auto_decision, step, "auto", adjusted, response)

        if getattr(self, "decision_mode", "llm") == "local_policy":
            policy = getattr(self, "policy", LocalPolicy())
            result = policy.decide(handler, state_data, adjusted)
            reasoning = f"[policy] {result.response}"
            self.tui.update_reasoning(reasoning)
            self.tui.add_decision(result.response, result.decision, result.elapsed_ms)
            self.tui.refresh()
            step.llm_response = result.response
            step.decision = result.decision
            step.elapsed_ms = result.elapsed_ms
            step.reasoning = reasoning
            self.trace_logger.add_step(step)
            self._emit("policy_decision", {
                "phase": "local_policy_decision",
                "decision_id": step.decision_id,
                "policy": policy.name,
                "command": result.response,
                "selected_candidate": result.selected_candidate,
            })
            print(f"\n[{handler.screen_type}] Policy: {result.response} ({result.elapsed_ms}ms)")
            return self._submit_decision(result.decision, step, "policy", adjusted, result.response)

        self._emit("llm_started", {"phase": "waiting_for_deepseek", "prompt": prompt})
        try:
            response, elapsed = self.llm.think(prompt)
            elapsed_ms = int(elapsed * 1000)
            self._emit("llm_finished", {"phase": "parsing_response", "response": response,
                                        "elapsed_ms": elapsed_ms})
            decision = handler.parse_response(response, state_data)
        except (LLMRequestError, InvalidDecisionError) as error:
            decision = handler.fallback_decision(state_data)
            if decision is None:
                message = f"[{handler.screen_type}] Decision stopped: {error}"
                self.tui.update_reasoning(message)
                self.tui.refresh()
                step.reasoning = message
                step.llm_response = locals().get("response", "")
                self.trace_logger.add_step(step)
                print(f"\n{message}")
                self._emit("decision_error", {"message": str(error), "prompt": prompt,
                                              "phase": "error"})
                return False

            message = (
                f"[{handler.screen_type}] Model decision failed: {error}; "
                f"using safe fallback {decision}"
            )
            self.tui.update_reasoning(message)
            self.tui.add_decision(locals().get("response", ""), decision, 0)
            self.tui.refresh()
            step.reasoning = message
            step.llm_response = locals().get("response", "")
            step.decision = decision
            self.trace_logger.add_step(step)
            print(f"\n{message}")
            return self._submit_decision(decision, step, "fallback", adjusted,
                                         locals().get("response", ""), str(error))

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

        print(f"\n[{handler.screen_type}] LLM: {response.strip()} -> {decision} ({elapsed_ms}ms)")

        return self._submit_decision(decision, step, "llm", adjusted, response)

    # ─── 辅助方法 ───────────────────────────────────────────

    def _emit(self, event_type: str, payload: dict) -> None:
        if not hasattr(self, "event_bus"):
            return
        try:
            current_state = getattr(self, "current_state_raw", {}) or {}
            self.event_bus.publish(
                event_type, payload, run_id=getattr(self, "current_run_id", ""),
                battle_id=getattr(self, "current_battle_id", ""),
                state_revision=int(current_state.get("state_revision", 0)),
            )
        except Exception as error:
            print(f"Telemetry warning: {error}")

    def _ensure_run(self, raw_state: dict) -> None:
        screen = raw_state.get("screen_type", "")
        if getattr(self, "current_run_id", "") or int(raw_state.get("act", 0)) <= 0 or screen == "MAIN_MENU":
            return
        self.current_run_id = uuid4().hex
        self.current_battle_id = uuid4().hex if raw_state.get("in_combat") else ""
        self.run_completed = False
        self._emit("run_started", {
            "character": raw_state.get("class", ""), "act": raw_state.get("act", 0),
            "floor": raw_state.get("floor", 0), "phase": "run_started",
        })

    def _settle_pending_transition(self, raw_state: dict) -> None:
        pending = getattr(self, "pending_transition", None)
        revision = int(raw_state.get("state_revision", 0))
        if not pending or revision <= pending["before_revision"]:
            return
        reward = self.reward_calculator.transition(pending["before_state"], raw_state)
        self.experience_store.add_transition(
            self.current_run_id, pending["before_state"], pending["action_key"],
            reward.total, "in_progress", self.policy_version,
        )
        self._emit("transition_observed", {
            "decision_id": pending["decision_id"], "reward": {
                "total": reward.total, "components": reward.components,
                "reward_version": reward.reward_version,
            }, "phase": "state_advanced",
        })
        self.pending_transition = None

    def _complete_run_if_needed(self, raw_state: dict) -> None:
        if not getattr(self, "current_run_id", "") or getattr(self, "run_completed", False):
            return
        screen = raw_state.get("screen_type", "")
        if screen not in {"GAME_OVER", "VICTORY"}:
            return
        result = "victory" if screen == "VICTORY" else "loss"
        terminal = self.reward_calculator.terminal({"result": result, "floor": raw_state.get("floor", 0)})
        self.experience_store.finalize_run(self.current_run_id, result, terminal.total)
        self._emit("run_completed", {"result": result, "floor": raw_state.get("floor", 0),
                                     "terminal_reward": terminal.total, "phase": "run_completed"})
        self._request_teacher_review(raw_state, result, terminal.total)
        self.run_completed = True

    def _request_teacher_review(self, raw_state: dict, result: str, terminal_reward: float) -> None:
        if not getattr(self, "teacher_review_on_run_end", False):
            return
        teacher = getattr(self, "teacher", None)
        if teacher is None:
            return
        summary = self._teacher_run_summary(raw_state, result, terminal_reward)
        self._emit("teacher_review_started", {
            "phase": "teacher_reviewing",
            "summary": summary,
        })
        review = teacher.review_run(summary)
        self._emit("teacher_review_finished", {
            "phase": "teacher_reviewed",
            **review,
        })

    def _teacher_run_summary(self, raw_state: dict, result: str, terminal_reward: float) -> dict:
        events, _gap = self.event_bus.events_after(0)
        recent = []
        for event in events[-40:]:
            data = event.to_dict()
            payload = data.get("payload", {})
            recent.append({
                "event_type": data.get("event_type"),
                "phase": payload.get("phase"),
                "command": payload.get("command"),
                "explanation": payload.get("explanation"),
                "reward": payload.get("reward"),
            })
        return {
            "result": result,
            "floor": raw_state.get("floor", 0),
            "act": raw_state.get("act", 0),
            "terminal_reward": terminal_reward,
            "recent_events": recent,
        }

    def _submit_decision(self, decision: Decision, step: DecisionStep, source: str,
                         candidates: list[dict], response: str, error: str = "") -> bool:
        current_state = getattr(self, "current_state_raw", {}) or {}
        selected = candidates[0] if candidates else None
        if decision.type == "choose_option":
            selected = next((item for item in candidates
                             if item.get("action_key") == f"choice:{decision.option_index}"), selected)
        explanation = explain_decision("COMBAT" if decision.type in {"play_card", "end_turn", "use_potion"}
                                       else "CHOICE", {}, selected, source)
        event_type = "fallback_selected" if source == "fallback" else "decision_parsed"
        payload = {
            "decision_id": step.decision_id, "source": source, "action": decision.to_json(),
            "command": decision.to_llm_format(), "explanation": explanation,
            "candidates": candidates, "prompt": step.prompt, "response": response,
            "elapsed_ms": step.elapsed_ms, "error": error, "pre_state": current_state,
            "phase": "submitting_action", "snapshot_patch": {"current_decision": {
                "decision_id": step.decision_id, "source": source, "action": decision.to_json(),
                "command": decision.to_llm_format(), "explanation": explanation,
                "candidates": candidates, "elapsed_ms": step.elapsed_ms,
            }},
        }
        self._emit(event_type, payload)
        self._emit("action_sent", {"decision_id": step.decision_id,
                                   "action": decision.to_json(), "phase": "submitting_action"})
        if not self.client.post_decision(decision):
            self._emit("action_rejected", {"decision_id": step.decision_id,
                                           "action": decision.to_json(), "phase": "action_rejected"})
            self.tui.update_reasoning("Action rejected by mod; waiting for a new state")
            return False
        self._emit("action_accepted", {"decision_id": step.decision_id,
                                       "action": decision.to_json(), "phase": "waiting_for_game"})
        self.pending_transition = {
            "decision_id": step.decision_id,
            "before_revision": int(current_state.get("state_revision", 0)),
            "before_state": deepcopy(current_state),
            "action_key": decision.to_llm_format(),
        }
        self.last_decision = decision
        return True

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
        "--decision-mode",
        choices=("local_policy", "llm"),
        default="",
        help="Realtime decision mode: local_policy avoids LLM calls; llm uses the configured backend",
    )
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
    decision_mode = args.decision_mode

    config_path = args.config
    if not args.mock and os.path.exists(config_path):
        try:
            import yaml
            with open(config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            llm_cfg = cfg.get("llm", {})
            if not backend:
                backend = llm_cfg.get("backend", "deepseek")
            if not model:
                model = llm_cfg.get("model", "")
            if not api_key:
                api_key = llm_cfg.get("api_key", "")
            if not decision_mode:
                decision_mode = cfg.get("agent", {}).get("decision_mode", "")
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
    if not decision_mode:
        decision_mode = "local_policy"

    agent = AIAgent(
        mod_host=args.host,
        mod_port=args.port,
        api_key=api_key,
        model=model,
        config_path=args.config if not args.mock else "",
        backend=backend,
        decision_mode=decision_mode,
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
