from __future__ import annotations

import json
import queue
import re
import threading
from pathlib import Path

from telemetry.events import TelemetryEvent


class TrainingDataWriter:
    """把运行事件转换为后续监督学习/离线强化学习使用的样本文件。"""

    def __init__(self, root: str | Path, queue_size: int = 2048):
        self.root = Path(root)
        self.training_dir = self.root / "training" / "runs"
        self.training_dir.mkdir(parents=True, exist_ok=True)
        self._pending_decisions: dict[tuple[str, str], dict] = {}
        self._queue: queue.Queue[TelemetryEvent | None] = queue.Queue(maxsize=queue_size)
        self.worker = threading.Thread(target=self._worker, name="training-data-writer", daemon=True)
        self.worker.start()

    @staticmethod
    def _valid(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9._-]+", value or ""))

    def log_guardrail_intervention(self, run_id: str, screen_type: str, rule: str,
                                    message: str, original_action: dict,
                                    corrected_action: dict | None = None) -> None:
        """记录护栏干预日志，作为训练时 teacher 标注的附加信号。"""
        path = self._run_dir(run_id) / "guardrail_interventions.jsonl"
        line = json.dumps({
            "schema_version": 1,
            "run_id": run_id,
            "screen_type": screen_type,
            "rule": rule,
            "message": message,
            "original_action": original_action,
            "corrected_action": corrected_action,
            "source": "guardrail",
        }, ensure_ascii=False, separators=(",", ":")) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def enqueue(self, event: TelemetryEvent) -> bool:
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            return False

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                self._write(item)
            finally:
                self._queue.task_done()

    def _write(self, event: TelemetryEvent) -> None:
        if not self._valid(event.run_id):
            return
        payload = event.payload
        decision_id = payload.get("decision_id", "")
        if event.event_type in {"decision_parsed", "fallback_selected"} and decision_id:
            self._pending_decisions[(event.run_id, decision_id)] = event.to_dict()
            return
        if event.event_type == "transition_observed" and decision_id:
            self._write_transition(event)
            return
        if event.event_type == "run_completed":
            self._write_json(event.run_id, "run_summary.json", {
                "schema_version": 1,
                "run_id": event.run_id,
                "timestamp_utc": event.timestamp_utc,
                **payload,
            })
            return
        if event.event_type == "teacher_review_finished":
            self._write_json(event.run_id, "teacher_review.json", {
                "schema_version": 1,
                "run_id": event.run_id,
                "timestamp_utc": event.timestamp_utc,
                **payload,
            })
            return
        if event.event_type == "teacher_stuck_review_finished":
            self._write_json(event.run_id, "teacher_stuck_review.json", {
                "schema_version": 1,
                "run_id": event.run_id,
                "timestamp_utc": event.timestamp_utc,
                **payload,
            })

    def _write_transition(self, event: TelemetryEvent) -> None:
        decision_id = event.payload.get("decision_id", "")
        decision = self._pending_decisions.get((event.run_id, decision_id))
        if not decision:
            return
        decision_payload = decision.get("payload", {})
        row = {
            "schema_version": 1,
            "run_id": event.run_id,
            "decision_id": decision_id,
            "timestamp_utc": decision.get("timestamp_utc"),
            "source": decision_payload.get("source", ""),
            "pre_state": decision_payload.get("pre_state", {}),
            "candidates": decision_payload.get("candidates", []),
            "chosen_action": decision_payload.get("action", {}),
            "command": decision_payload.get("command", ""),
            "explanation": decision_payload.get("explanation", ""),
            "reward": event.payload.get("reward", {}),
            "outcome": "in_progress",
            "guardrail": decision_payload.get("guardrail"),
        }
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        path = self._run_dir(event.run_id) / "transitions.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def _write_json(self, run_id: str, name: str, data: dict) -> None:
        path = self._run_dir(run_id) / name
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def _run_dir(self, run_id: str) -> Path:
        path = self.training_dir / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def flush(self, timeout: float = 5.0) -> None:
        done = threading.Event()
        threading.Thread(target=lambda: (self._queue.join(), done.set()), daemon=True).start()
        if not done.wait(timeout):
            raise TimeoutError("training data queue did not flush")

    def close(self) -> None:
        if not self.worker.is_alive():
            return
        self.flush()
        self._queue.put(None)
        self.worker.join(timeout=5)
