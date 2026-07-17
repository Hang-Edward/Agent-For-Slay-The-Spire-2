from __future__ import annotations

import json
import queue
import re
import threading
from pathlib import Path

from telemetry.events import CRITICAL_EVENT_TYPES, TelemetryEvent


class RunHistoryStore:
    def __init__(self, root: str | Path, queue_size: int = 2048):
        self.root = Path(root)
        self.runs_dir = self.root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._queue: queue.Queue[TelemetryEvent | None] = queue.Queue(maxsize=queue_size)
        self.worker = threading.Thread(target=self._worker, name="run-history-writer", daemon=True)
        self.worker.start()

    @staticmethod
    def _valid(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9._-]+", value or ""))

    def enqueue(self, event: TelemetryEvent) -> bool:
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            if event.event_type not in CRITICAL_EVENT_TYPES:
                return False
            try:
                self._queue.put(event, timeout=0.05)
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
        run_dir = self.runs_dir / event.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        data = event.to_dict()
        line = json.dumps(data, ensure_ascii=False) + "\n"
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(line)
        if event.event_type in {"decision_parsed", "fallback_selected", "decision_error"}:
            with (run_dir / "decisions.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(line)
        manifest_path = run_dir / "manifest.json"
        manifest = self._read_json(manifest_path) or {"run_id": event.run_id, "status": "active"}
        if event.event_type == "run_started":
            manifest.update(event.payload)
        elif event.event_type == "run_completed":
            manifest.update(event.payload)
            manifest["status"] = "completed"
        elif event.event_type == "run_aborted":
            manifest.update(event.payload)
            manifest["status"] = "aborted"
        manifest["last_sequence"] = event.sequence
        temp = manifest_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(manifest_path)

    @staticmethod
    def _read_json(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        rows = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
        return rows

    def flush(self, timeout: float = 5.0) -> None:
        done = threading.Event()
        threading.Thread(target=lambda: (self._queue.join(), done.set()), daemon=True).start()
        if not done.wait(timeout):
            raise TimeoutError("history queue did not flush")

    def close(self) -> None:
        if not self.worker.is_alive():
            return
        self.flush()
        self._queue.put(None)
        self.worker.join(timeout=5)

    def list_runs(self, *, offset: int = 0, limit: int = 50) -> list[dict]:
        rows = [self._read_json(path) for path in self.runs_dir.glob("*/manifest.json")]
        rows = [row for row in rows if row]
        rows.sort(key=lambda row: row.get("last_sequence", 0), reverse=True)
        return rows[offset:offset + limit]

    def get_run(self, run_id: str, *, offset: int = 0, limit: int = 200) -> dict | None:
        if not self._valid(run_id):
            return None
        run_dir = self.runs_dir / run_id
        manifest = self._read_json(run_dir / "manifest.json")
        if manifest is None:
            return None
        events = self._read_jsonl(run_dir / "events.jsonl")
        return {**manifest, "events": events[offset:offset + limit]}

    def get_decision(self, run_id: str, decision_id: str) -> dict | None:
        if not self._valid(run_id) or not self._valid(decision_id):
            return None
        for row in self._read_jsonl(self.runs_dir / run_id / "decisions.jsonl"):
            if row.get("payload", {}).get("decision_id") == decision_id:
                return row
        return None

    def recover_interrupted_runs(self, active_run_fingerprint: str = "") -> None:
        for manifest in self.list_runs(limit=10000):
            if manifest.get("status") != "active":
                continue
            if active_run_fingerprint and active_run_fingerprint in manifest.get("fingerprints", []):
                continue
            sequence = int(manifest.get("last_sequence", 0)) + 1
            self.enqueue(TelemetryEvent.create(
                sequence=sequence, event_type="run_aborted", run_id=manifest["run_id"],
                payload={"reason": "agent_interrupted"},
            ))
