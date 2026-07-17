# AI Decision Dashboard and Experience Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local read-only dashboard on port `18889` that streams explainable Agent decisions, persists complete run histories, and uses confidence-bounded historical experience to improve later decisions.

**Architecture:** Add a typed telemetry event source at the Python Agent orchestration boundary. A bounded event bus feeds an asynchronous JSONL/SQLite history store and a standard-library HTTP/SSE server, while the existing Mod remains unchanged on port `18888`. Historical evidence is retrieved through a separate learning service and applied as a capped adjustment over existing strategy scores.

**Tech Stack:** Python 3.10+, standard-library `dataclasses`, `threading`, `queue`, `http.server`, `sqlite3`, JSONL, SSE, plain HTML/CSS/JavaScript, pytest, Playwright for final browser verification.

## Global Constraints

- Keep Mod port `18888` and its existing `/state`, `/status`, and `/decision` contract unchanged.
- Bind the dashboard only to `127.0.0.1:18889`.
- Dashboard APIs are GET-only; unsupported methods return `405`.
- Dashboard, browser, persistence, and learning failures must not block gameplay.
- Never publish or persist API keys, bearer tokens, authorization headers, or secret configuration values.
- Render model output, Prompt text, and JSON as text, never executable HTML.
- Preserve complete local histories under `data/`, and ignore `data/` and `.superpowers/` in Git.
- Do not add Node.js or a frontend build chain.
- Do not claim to expose hidden chain of thought; display only real state, scores, prompts, responses, and derived explanations.
- Runtime histories and generated databases are never committed.
- Commit steps in this plan are gated by explicit user authorization; skip them during execution unless the user asks to commit.
- Design reference: `docs/superpowers/specs/2026-07-17-ai-decision-dashboard-design.md`.

---

## File Structure

```text
engine/
  telemetry/
    __init__.py              Public telemetry exports
    events.py                Typed event schema and sequence-safe serialization
    redaction.py             Recursive secret redaction
    event_bus.py             Bounded ring, condition variable, snapshot, subscribers
  history/
    __init__.py
    run_store.py             Async JSONL archives, manifests, recovery, history reads
    rewards.py               Versioned immediate, room, and terminal rewards
  learning/
    __init__.py
    fingerprints.py          Stable state feature fingerprints
    experience_store.py      SQLite transition index and similarity queries
    experience_service.py    Confidence, shrinkage, capped score adjustment
  explanation/
    __init__.py
    decision_explainer.py    Candidate extraction and auditable explanation summary
  dashboard/
    __init__.py
    server.py                Read-only REST, static assets, and SSE
    static/
      index.html             Command-center shell and accessible tabs
      styles.css             Responsive three-column layout
      app.js                 Snapshot, SSE, history, Debug rendering
  requirements-dev.txt      Reproducible pytest and Playwright test tooling
  tests/
    test_telemetry_events.py
    test_event_bus.py
    test_run_store.py
    test_rewards.py
    test_experience_learning.py
    test_decision_explainer.py
    test_dashboard_api.py
    test_agent_telemetry.py
    test_dashboard_e2e.py
  main.py                    Agent lifecycle and decision telemetry integration
config/
  ai_config.yaml             Dashboard and experience-learning settings
.gitignore                   Runtime data and visual-companion ignores
run.ps1                      Optional dashboard port passthrough
architecture/README.md       User-facing run and dashboard instructions
```

---

### Task 1: Typed Telemetry Events and Secret Redaction

**Files:**
- Create: `engine/requirements-dev.txt`
- Create: `engine/telemetry/__init__.py`
- Create: `engine/telemetry/events.py`
- Create: `engine/telemetry/redaction.py`
- Test: `engine/tests/test_telemetry_events.py`

**Interfaces:**
- Produces: `TelemetryEvent`, `CRITICAL_EVENT_TYPES`, `redact_secrets(value, secret_values=())`.
- Consumed by: Tasks 2, 3, 6, and 7.

- [ ] **Step 1: Add and install reproducible test dependencies**

```text
# engine/requirements-dev.txt
-r requirements.txt
pytest>=8.0,<9
```

Run: `engine\venv\Scripts\python.exe -m pip install -r engine\requirements-dev.txt`

Expected: exit code `0`, followed by `engine\venv\Scripts\python.exe -m pytest --version` printing pytest 8.x.

- [ ] **Step 2: Write failing event and redaction tests**

```python
# engine/tests/test_telemetry_events.py
from telemetry.events import TelemetryEvent
from telemetry.redaction import redact_secrets


def test_event_serializes_stable_envelope():
    event = TelemetryEvent.create(
        sequence=7,
        event_type="llm_started",
        run_id="run-1",
        battle_id="battle-1",
        state_revision=42,
        payload={"prompt": "choose"},
        timestamp_utc="2026-07-17T05:00:00.000Z",
    )
    assert event.to_dict() == {
        "schema_version": 1,
        "event_id": event.event_id,
        "sequence": 7,
        "timestamp_utc": "2026-07-17T05:00:00.000Z",
        "run_id": "run-1",
        "battle_id": "battle-1",
        "state_revision": 42,
        "event_type": "llm_started",
        "payload": {"prompt": "choose"},
    }


def test_redaction_is_recursive_and_case_insensitive():
    value = {
        "Authorization": "Bearer secret-token",
        "nested": {"api_key": "secret-token", "text": "prefix secret-token suffix"},
        "items": [{"token": "abc"}, "secret-token"],
    }
    result = redact_secrets(value, secret_values=("secret-token", "abc"))
    assert result["Authorization"] == "[REDACTED]"
    assert result["nested"]["api_key"] == "[REDACTED]"
    assert result["nested"]["text"] == "prefix [REDACTED] suffix"
    assert result["items"] == [{"token": "[REDACTED]"}, "[REDACTED]"]
```

- [ ] **Step 3: Run the tests and verify the import failure**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_telemetry_events.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'telemetry.events'`.

- [ ] **Step 4: Implement immutable events and recursive redaction**

```python
# engine/telemetry/events.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

CRITICAL_EVENT_TYPES = frozenset({
    "run_started", "run_resumed", "llm_started", "llm_finished",
    "decision_parsed", "fallback_selected", "action_sent", "action_accepted",
    "action_rejected", "decision_error", "run_completed", "run_aborted",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    schema_version: int
    event_id: str
    sequence: int
    timestamp_utc: str
    run_id: str
    battle_id: str
    state_revision: int
    event_type: str
    payload: dict = field(default_factory=dict)

    @classmethod
    def create(cls, *, sequence: int, event_type: str, run_id: str = "",
               battle_id: str = "", state_revision: int = 0,
               payload: dict | None = None, timestamp_utc: str | None = None) -> "TelemetryEvent":
        return cls(1, uuid4().hex, sequence, timestamp_utc or _utc_now(), run_id,
                   battle_id, state_revision, event_type, payload or {})

    def to_dict(self) -> dict:
        return asdict(self)
```

```python
# engine/telemetry/redaction.py
from __future__ import annotations

SECRET_KEYS = {"authorization", "api_key", "apikey", "token", "access_token", "secret"}


def redact_secrets(value, secret_values: tuple[str, ...] = ()):
    secrets = tuple(secret for secret in secret_values if secret)
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in SECRET_KEYS
            else redact_secrets(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item, secrets) for item in value)
    if isinstance(value, str):
        result = value
        for secret in secrets:
            result = result.replace(secret, "[REDACTED]")
        return result
    return value
```

Export the public names from `engine/telemetry/__init__.py`.

- [ ] **Step 5: Run the focused tests**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_telemetry_events.py -v`

Expected: 2 tests PASS.

- [ ] **Step 6: Commit after explicit authorization**

```powershell
git add engine/requirements-dev.txt engine/telemetry engine/tests/test_telemetry_events.py
git commit -m "feat: add typed telemetry events and redaction"
```

---

### Task 2: Bounded Event Bus and Reconnect Buffer

**Files:**
- Create: `engine/telemetry/event_bus.py`
- Modify: `engine/telemetry/__init__.py`
- Test: `engine/tests/test_event_bus.py`

**Interfaces:**
- Consumes: `TelemetryEvent`, `CRITICAL_EVENT_TYPES`, `redact_secrets` from Task 1.
- Produces: `DecisionEventBus.publish()`, `snapshot()`, `events_after()`, and `wait_for_events()`.
- Consumed by: Dashboard server, Agent integration, and history writer.

- [ ] **Step 1: Write failing ring-buffer and wait tests**

```python
# engine/tests/test_event_bus.py
import threading

from telemetry.event_bus import DecisionEventBus


def test_ring_reports_gap_and_keeps_latest_events():
    bus = DecisionEventBus(max_events=2)
    bus.publish("state_received", {"n": 1})
    bus.publish("state_received", {"n": 2})
    bus.publish("decision_parsed", {"n": 3})
    events, gap = bus.events_after(0)
    assert gap is True
    assert [event.sequence for event in events] == [2, 3]


def test_wait_for_events_wakes_on_publish():
    bus = DecisionEventBus(max_events=5)
    timer = threading.Timer(0.02, lambda: bus.publish("llm_started", {}))
    timer.start()
    events, gap = bus.wait_for_events(0, timeout=0.2)
    timer.join()
    assert gap is False
    assert [event.event_type for event in events] == ["llm_started"]


def test_snapshot_tracks_latest_phase():
    bus = DecisionEventBus(max_events=5)
    bus.publish("state_received", {"phase": "reading_state",
                "snapshot_patch": {"game_state": {"floor": 8}}}, state_revision=8)
    bus.publish("llm_started", {"phase": "waiting_for_deepseek",
                "snapshot_patch": {"current_decision": {"status": "thinking"}}}, state_revision=8)
    snapshot = bus.snapshot()
    assert snapshot["phase"] == "waiting_for_deepseek"
    assert snapshot["state_revision"] == 8
    assert snapshot["game_state"]["floor"] == 8
    assert snapshot["current_decision"]["status"] == "thinking"
```

- [ ] **Step 2: Verify the tests fail**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_event_bus.py -v`

Expected: FAIL because `DecisionEventBus` does not exist.

- [ ] **Step 3: Implement the thread-safe bus**

```python
# engine/telemetry/event_bus.py
from __future__ import annotations

from collections import deque
from copy import deepcopy
from threading import Condition

from .events import TelemetryEvent
from .redaction import redact_secrets


class DecisionEventBus:
    def __init__(self, max_events: int = 500, secret_values: tuple[str, ...] = ()):
        self._events: deque[TelemetryEvent] = deque(maxlen=max_events)
        self._condition = Condition()
        self._sequence = 0
        self._secret_values = secret_values
        self._snapshot = {"phase": "starting", "state_revision": 0, "last_event": None}
        self._sinks = []

    def add_sink(self, sink) -> None:
        self._sinks.append(sink)

    def publish(self, event_type: str, payload: dict, *, run_id: str = "",
                battle_id: str = "", state_revision: int = 0) -> TelemetryEvent:
        clean = redact_secrets(payload, self._secret_values)
        with self._condition:
            self._sequence += 1
            event = TelemetryEvent.create(
                sequence=self._sequence, event_type=event_type, run_id=run_id,
                battle_id=battle_id, state_revision=state_revision, payload=clean,
            )
            self._events.append(event)
            patch = clean.get("snapshot_patch", {})
            if isinstance(patch, dict):
                self._snapshot.update(deepcopy(patch))
            self._snapshot.update({
                "phase": clean.get("phase", self._snapshot["phase"]),
                "state_revision": state_revision or self._snapshot["state_revision"],
                "last_event": event.to_dict(),
            })
            self._condition.notify_all()
        for sink in tuple(self._sinks):
            try:
                sink.enqueue(event)
            except Exception:
                continue
        return event

    def snapshot(self) -> dict:
        with self._condition:
            return deepcopy(self._snapshot)

    def events_after(self, sequence: int) -> tuple[list[TelemetryEvent], bool]:
        with self._condition:
            events = list(self._events)
        gap = bool(events and sequence < events[0].sequence - 1)
        return [event for event in events if event.sequence > sequence], gap

    def wait_for_events(self, sequence: int, timeout: float) -> tuple[list[TelemetryEvent], bool]:
        with self._condition:
            if self._sequence <= sequence:
                self._condition.wait(timeout)
        return self.events_after(sequence)
```

- [ ] **Step 4: Run focused tests and the existing suite**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_event_bus.py engine/tests/test_protocol.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit after explicit authorization**

```powershell
git add engine/telemetry engine/tests/test_event_bus.py
git commit -m "feat: add bounded telemetry event bus"
```

---

### Task 3: Persistent Run Archives and Crash Recovery

**Files:**
- Create: `engine/history/__init__.py`
- Create: `engine/history/run_store.py`
- Test: `engine/tests/test_run_store.py`

**Interfaces:**
- Consumes: `TelemetryEvent` from Task 1.
- Produces: `RunHistoryStore.enqueue()`, `flush()`, `close()`, `list_runs()`, `get_run()`, `get_decision()`, and `recover_interrupted_runs()`.
- Consumed by: Event bus sink and dashboard history API.

- [ ] **Step 1: Write failing archive, malformed-tail, and recovery tests**

```python
# engine/tests/test_run_store.py
import json

from history.run_store import RunHistoryStore
from telemetry.events import TelemetryEvent


def event(sequence, event_type, run_id="run-1", payload=None):
    return TelemetryEvent.create(sequence=sequence, event_type=event_type,
                                 run_id=run_id, payload=payload or {})


def test_store_persists_manifest_events_and_decisions(tmp_path):
    store = RunHistoryStore(tmp_path)
    store.enqueue(event(1, "run_started", payload={"character": "IRONCLAD"}))
    store.enqueue(event(2, "decision_parsed", payload={"decision_id": "d1", "action": "END"}))
    store.enqueue(event(3, "run_completed", payload={"result": "loss", "floor": 9}))
    store.flush()
    assert store.list_runs()[0]["run_id"] == "run-1"
    assert store.get_decision("run-1", "d1")["payload"]["action"] == "END"
    store.close()


def test_reader_skips_malformed_final_jsonl_line(tmp_path):
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": "run-1"}), encoding="utf-8")
    (run_dir / "events.jsonl").write_text('{"sequence":1}\n{"broken":', encoding="utf-8")
    store = RunHistoryStore(tmp_path)
    assert store.get_run("run-1")["events"] == [{"sequence": 1}]
    store.close()


def test_recovery_marks_unmatched_active_run_aborted(tmp_path):
    store = RunHistoryStore(tmp_path)
    store.enqueue(event(1, "run_started"))
    store.flush()
    store.recover_interrupted_runs(active_run_fingerprint="different")
    store.flush()
    assert store.list_runs()[0]["status"] == "aborted"
    store.close()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_run_store.py -v`

Expected: FAIL because `history.run_store` does not exist.

- [ ] **Step 3: Implement the bounded asynchronous writer**

Implement `RunHistoryStore(root: Path, queue_size: int = 2048)` with these exact public signatures: `enqueue(event: TelemetryEvent) -> bool`, `flush(timeout: float = 5.0) -> None`, `close() -> None`, `list_runs(offset: int = 0, limit: int = 50) -> list[dict]`, `get_run(run_id: str, offset: int = 0, limit: int = 200) -> dict`, `get_decision(run_id: str, decision_id: str) -> dict | None`, and `recover_interrupted_runs(active_run_fingerprint: str = "") -> None`.

The worker writes every event to `events.jsonl`, additionally writes `decision_parsed`, `fallback_selected`, and `decision_error` to `decisions.jsonl`, and atomically replaces `manifest.json` through `manifest.json.tmp`. Validate IDs with `re.fullmatch(r"[A-Za-z0-9._-]+", value)` before resolving paths. `enqueue()` uses `put_nowait`; if full, it may reject `state_received`, but it retries critical events for at most 50 ms and reports failure to the caller without raising.

- [ ] **Step 4: Run focused tests**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_run_store.py -v`

Expected: 3 tests PASS and no writer thread remains after `close()`.

- [ ] **Step 5: Commit after explicit authorization**

```powershell
git add engine/history engine/tests/test_run_store.py
git commit -m "feat: persist run histories with recovery"
```

---

### Task 4: Versioned Reward Calculation

**Files:**
- Create: `engine/history/rewards.py`
- Test: `engine/tests/test_rewards.py`

**Interfaces:**
- Produces: `RewardBreakdown`, `RewardCalculator.transition()`, `room()`, and `terminal()`.
- Consumed by: Experience store and Agent state-transition integration.

- [ ] **Step 1: Write failing reward tests**

```python
# engine/tests/test_rewards.py
from history.rewards import RewardCalculator


def state(player_hp, monster_hp, floor=1, gold=0):
    return {"player": {"current_hp": player_hp, "gold": gold},
            "monsters": [{"id": "m", "current_hp": monster_hp}], "floor": floor}


def test_transition_penalizes_hp_loss_and_rewards_enemy_damage():
    reward = RewardCalculator().transition(state(50, 30), state(45, 20))
    assert reward.components["player_hp_delta"] < 0
    assert reward.components["enemy_hp_delta"] > 0
    assert reward.total == round(sum(reward.components.values()), 4)


def test_terminal_outcome_dominates_shaping():
    calculator = RewardCalculator()
    win = calculator.terminal({"result": "victory", "floor": 50})
    loss = calculator.terminal({"result": "loss", "floor": 49})
    assert win.total > loss.total + 50
    assert win.reward_version == "1"
```

- [ ] **Step 2: Verify failure**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_rewards.py -v`

Expected: FAIL because `history.rewards` does not exist.

- [ ] **Step 3: Implement transparent reward components**

```python
# engine/history/rewards.py
from dataclasses import dataclass


@dataclass(frozen=True)
class RewardBreakdown:
    total: float
    components: dict[str, float]
    reward_version: str = "1"


class RewardCalculator:
    def _result(self, components: dict[str, float]) -> RewardBreakdown:
        return RewardBreakdown(round(sum(components.values()), 4), components)

    def transition(self, before: dict, after: dict) -> RewardBreakdown:
        before_enemy = sum(max(0, int(m.get("current_hp", 0))) for m in before.get("monsters", []))
        after_enemy = sum(max(0, int(m.get("current_hp", 0))) for m in after.get("monsters", []))
        hp_delta = int(after.get("player", {}).get("current_hp", 0)) - int(before.get("player", {}).get("current_hp", 0))
        return self._result({
            "player_hp_delta": hp_delta * 2.0,
            "enemy_hp_delta": max(0, before_enemy - after_enemy) * 0.25,
            "floor_progress": max(0, int(after.get("floor", 0)) - int(before.get("floor", 0))) * 5.0,
        })

    def room(self, summary: dict) -> RewardBreakdown:
        return self._result({"room_victory": 12.0 if summary.get("won") else -20.0,
                             "remaining_hp_ratio": float(summary.get("hp_ratio", 0)) * 5.0})

    def terminal(self, summary: dict) -> RewardBreakdown:
        victory = summary.get("result") == "victory"
        return self._result({"run_result": 100.0 if victory else -50.0,
                             "floor_progress": float(summary.get("floor", 0)) * 1.5})
```

Extend transition components during implementation with block use, energy waste, consumable use, gold, and kill prevention using fields present in state snapshots. Keep all coefficients centralized and tested.

- [ ] **Step 4: Run reward and strategy regressions**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_rewards.py engine/tests/test_strategy.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit after explicit authorization**

```powershell
git add engine/history/rewards.py engine/tests/test_rewards.py
git commit -m "feat: add versioned run reward model"
```

---

### Task 5: SQLite Experience Index and Confidence-Bounded Learning

**Files:**
- Create: `engine/learning/__init__.py`
- Create: `engine/learning/fingerprints.py`
- Create: `engine/learning/experience_store.py`
- Create: `engine/learning/experience_service.py`
- Test: `engine/tests/test_experience_learning.py`

**Interfaces:**
- Consumes: decision records and `RewardBreakdown`.
- Produces: `state_fingerprint()`, `ExperienceStore.add_transition()`, `query_similar()`, and `ExperienceService.apply()`.
- Consumed by: Agent integration and dashboard decision evidence.

- [ ] **Step 1: Write failing fingerprint, threshold, shrinkage, and cap tests**

```python
# engine/tests/test_experience_learning.py
from learning.experience_service import ExperienceService
from learning.experience_store import ExperienceStore
from learning.fingerprints import state_fingerprint


def context():
    return {"screen_type": "COMBAT", "act": 1, "floor": 8,
            "player": {"current_hp": 40, "max_hp": 80},
            "monsters": [{"id": "jaw_worm"}], "deck": [{"id": "Strike"}]}


def test_fingerprint_is_stable_for_equivalent_state():
    assert state_fingerprint(context()) == state_fingerprint(dict(context()))


def test_learning_requires_minimum_samples_and_caps_adjustment(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite3")
    service = ExperienceService(store, minimum_samples=3, max_adjustment=1.5)
    candidates = [{"action_key": "END", "score": 4.0}]
    for reward in (5.0, 6.0):
        store.add_transition("run-1", context(), "END", reward, "in_progress", "policy-1")
    assert service.apply(context(), candidates)[0]["final_score"] == 4.0
    store.add_transition("run-1", context(), "END", 100.0, "in_progress", "policy-1")
    store.finalize_run("run-1", "victory", terminal_reward=100.0)
    adjusted = service.apply(context(), candidates)[0]
    assert 4.0 < adjusted["final_score"] <= 5.5
    assert adjusted["sample_count"] == 3
    store.close()
```

- [ ] **Step 2: Verify failure**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_experience_learning.py -v`

Expected: FAIL because the learning package does not exist.

- [ ] **Step 3: Implement stable features and SQLite schema**

Use canonical JSON with sorted keys and a SHA-256 digest. Store queryable dimensions beside the digest:

```sql
CREATE TABLE IF NOT EXISTS experiences (
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  screen_type TEXT NOT NULL,
  character TEXT NOT NULL,
  act INTEGER NOT NULL,
  hp_band INTEGER NOT NULL,
  enemy_key TEXT NOT NULL,
  action_key TEXT NOT NULL,
  shaped_reward REAL NOT NULL,
  terminal_reward REAL NOT NULL DEFAULT 0,
  outcome TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  created_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experience_lookup
ON experiences(screen_type, character, act, hp_band, enemy_key, action_key);
```

`ExperienceStore.add_transition(run_id, context, action_key, shaped_reward, outcome, policy_version)` inserts one row. `ExperienceStore.finalize_run(run_id, outcome, terminal_reward)` updates every row from that run exactly once. `ExperienceStore.query_similar(context, action_key, limit=200)` returns `reward = shaped_reward + terminal_reward`, first matching screen, character, Act, HP band, enemy key, and action. If no exact rows exist, relax only HP band by one bucket; do not mix different screen types.

- [ ] **Step 4: Implement confidence adjustment**

```python
class ExperienceService:
    def __init__(self, store, minimum_samples=5, prior_weight=10.0, max_adjustment=1.5):
        self.store = store
        self.minimum_samples = minimum_samples
        self.prior_weight = prior_weight
        self.max_adjustment = max_adjustment

    def apply(self, context: dict, candidates: list[dict]) -> list[dict]:
        output = []
        for candidate in candidates:
            rows = self.store.query_similar(context, candidate["action_key"])
            sample_count = len(rows)
            mean_reward = sum(row["reward"] for row in rows) / sample_count if rows else 0.0
            confidence = sample_count / (sample_count + self.prior_weight)
            adjustment = 0.0 if sample_count < self.minimum_samples else max(
                -self.max_adjustment, min(self.max_adjustment, mean_reward * 0.05 * confidence)
            )
            output.append({**candidate, "baseline_score": candidate["score"],
                           "historical_adjustment": round(adjustment, 3),
                           "final_score": round(candidate["score"] + adjustment, 3),
                           "sample_count": sample_count, "confidence": round(confidence, 3)})
        return sorted(output, key=lambda item: item["final_score"], reverse=True)
```

- [ ] **Step 5: Run learning tests**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_experience_learning.py engine/tests/test_strategy.py -v`

Expected: all tests PASS and the temporary SQLite database closes cleanly.

- [ ] **Step 6: Commit after explicit authorization**

```powershell
git add engine/learning engine/tests/test_experience_learning.py
git commit -m "feat: learn from confidence-bounded run experience"
```

---

### Task 6: Decision Explanation and Agent Telemetry Integration

**Files:**
- Create: `engine/explanation/__init__.py`
- Create: `engine/explanation/decision_explainer.py`
- Modify: `engine/main.py`
- Modify: `engine/trace/decision_trace.py`
- Modify: `engine/trace/trace_logger.py`
- Test: `engine/tests/test_decision_explainer.py`
- Test: `engine/tests/test_agent_telemetry.py`

**Interfaces:**
- Consumes: event bus, history store, reward calculator, experience service, handler `state_data`.
- Produces: one coherent telemetry stream for TUI, history, dashboard, and learning.
- Preserves: current action validation and fallback behavior.

- [ ] **Step 1: Write failing candidate-normalization and explanation tests**

```python
# engine/tests/test_decision_explainer.py
from explanation.decision_explainer import (
    explain_decision,
    format_experience_evidence,
    normalized_candidates,
)


def test_combat_candidates_preserve_baseline_and_risk():
    state_data = {"turn_plan": {"candidate_sequences": [
        {"cards": [1, 2], "score": 8.7, "estimated_hp_loss": 9},
        {"cards": [2, 0], "score": 6.1, "estimated_hp_loss": 17},
    ]}}
    candidates = normalized_candidates("COMBAT", state_data)
    assert candidates[0]["action_key"] == "cards:1,2"
    assert candidates[0]["score"] == 8.7
    summary = explain_decision("COMBAT", state_data, candidates[0], "llm")
    assert "9" in summary
    assert "LLM" in summary


def test_choice_candidates_include_route_and_card_scores():
    state_data = {"options": [{"index": 0}, {"index": 1}],
                  "route_scores": [{"option_index": 0, "score": 4.2}],
                  "card_evaluations": {1: {"score": 2.0, "reasons": ["fills block gap"]}}}
    keys = {item["action_key"] for item in normalized_candidates("CHOICE", state_data)}
    assert keys == {"choice:0", "choice:1"}


def test_experience_prompt_text_is_compact_and_auditable():
    text = format_experience_evidence([{
        "action_key": "choice:1", "baseline_score": 2.0,
        "historical_adjustment": 0.4, "final_score": 2.4,
        "sample_count": 12, "confidence": 0.55,
    }])
    assert "choice:1" in text
    assert "samples=12" in text
    assert "baseline=2.0" in text
    assert len(text) < 500
```

- [ ] **Step 2: Write a failing Agent lifecycle test**

```python
# engine/tests/test_agent_telemetry.py
from types import SimpleNamespace

from main import AIAgent
from telemetry.event_bus import DecisionEventBus


def test_agent_emits_llm_and_action_lifecycle(monkeypatch):
    agent = object.__new__(AIAgent)
    agent.event_bus = DecisionEventBus()
    agent.skills_registry = SimpleNamespace(get_enabled_instructions=lambda: "", enabled_skills=[])
    agent.experience_service = SimpleNamespace(apply=lambda _ctx, items: items)
    agent.llm = SimpleNamespace(think=lambda _prompt: ("END", 0.1), name="test")
    agent.client = SimpleNamespace(post_decision=lambda _decision: True)
    agent.tui = SimpleNamespace(update_reasoning=lambda *_: None, add_decision=lambda *_: None,
                                refresh=lambda: None)
    agent.trace_logger = SimpleNamespace(add_step=lambda *_: None)
    agent.current_run_id = "run-1"
    agent.current_battle_id = "battle-1"
    agent.current_state_raw = {"state_revision": 5, "screen_type": "COMBAT"}
    handler = SimpleNamespace(
        screen_type="COMBAT", build_prompt=lambda *_: "prompt", try_auto_decision=lambda *_: None,
        parse_response=lambda *_: __import__("communication.protocol", fromlist=["Decision"]).Decision.end_turn(),
    )
    assert agent._make_decision(SimpleNamespace(turn=1), handler, {}) is True
    names = [event.event_type for event in agent.event_bus.events_after(0)[0]]
    assert names == ["candidates_scored", "llm_started", "llm_finished",
                     "decision_parsed", "action_sent", "action_accepted"]
```

- [ ] **Step 3: Verify both test files fail**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_decision_explainer.py engine/tests/test_agent_telemetry.py -v`

Expected: FAIL because explanation code and Agent event integration do not exist.

- [ ] **Step 4: Implement normalized candidates and concise explanations**

`normalized_candidates(screen_type, state_data)` maps:

- Combat sequence `{cards, score, estimated_hp_loss}` to `action_key="cards:<indices>"`.
- Route score to `action_key="choice:<option_index>"`.
- Card evaluation to `action_key="choice:<option_index>"`.
- Unscored legal options to baseline score `0.0`.

`explain_decision()` returns a short factual Chinese summary using candidate score, HP-loss estimate, route room counts, deck-fit reasons, historical adjustment, and source. It must never invent a model rationale.

Add this exact compact Prompt formatter:

```python
def format_experience_evidence(candidates: list[dict], limit: int = 5) -> str:
    rows = [item for item in candidates if int(item.get("sample_count", 0)) > 0][:limit]
    if not rows:
        return ""
    lines = ["Historical experience evidence (advisory; current legal state wins):"]
    for item in rows:
        lines.append(
            f"- {item['action_key']}: baseline={item['baseline_score']}, "
            f"history={item['historical_adjustment']:+.3f}, final={item['final_score']}, "
            f"samples={item['sample_count']}, confidence={item['confidence']:.3f}"
        )
    return "\n".join(lines)
```

- [ ] **Step 5: Wire lifecycle events into `AIAgent`**

Extend `DecisionStep` with a stable ID while preserving existing constructor compatibility:

```python
from dataclasses import dataclass, field
from uuid import uuid4

@dataclass
class DecisionStep:
    turn: int
    prompt: str
    llm_response: str
    decision: Decision
    reasoning: str = ""
    elapsed_ms: int = 0
    state_snapshot: str = ""
    decision_id: str = field(default_factory=lambda: uuid4().hex)
```

In `AIAgent.__init__`, construct optional collaborators through injected defaults:

```python
self.event_bus = event_bus or DecisionEventBus(secret_values=(api_key,))
self.history_store = history_store or RunHistoryStore(data_dir)
self.event_bus.add_sink(self.history_store)
self.reward_calculator = RewardCalculator()
self.experience_store = ExperienceStore(os.path.join(data_dir, "experience.sqlite3"))
self.experience_service = ExperienceService(self.experience_store)
self.current_run_id = ""
self.current_battle_id = ""
self.pending_transition = None
```

Publish each event immediately around the existing operation. Do not change when an action is allowed or how responses are parsed. Use one helper:

```python
def _emit(self, event_type: str, payload: dict) -> None:
    try:
        self.event_bus.publish(event_type, payload, run_id=self.current_run_id,
                               battle_id=self.current_battle_id,
                               state_revision=int((self.current_state_raw or {}).get("state_revision", 0)))
    except Exception as error:
        print(f"Telemetry warning: {error}")
```

Ensure `finally` closes the dashboard, history writer, experience store, and TUI independently so one close error cannot suppress the others.

Before building the Prompt, normalize and adjust candidates, then append only compact evidence to strategy instructions:

```python
candidates = normalized_candidates(handler.screen_type, state_data)
adjusted_candidates = self.experience_service.apply(self.current_state_raw, candidates)
state_data["experience_evidence"] = adjusted_candidates
experience_text = format_experience_evidence(adjusted_candidates)
combined_instructions = "\n".join(part for part in (strategy_instructions, experience_text) if part)
prompt = handler.build_prompt(state_data, combined_instructions)
self._emit("candidates_scored", {"candidates": adjusted_candidates, "phase": "evaluating_candidates"})
```

When an action is accepted by the Mod, save a pending transition instead of assigning reward immediately:

```python
self.pending_transition = {
    "decision_id": step.decision_id,
    "before_revision": int(self.current_state_raw.get("state_revision", 0)),
    "before_state": deepcopy(self.current_state_raw),
    "action_key": decision.to_llm_format(),
    "policy_version": self.policy_version,
}
```

At the beginning of `_run_iteration`, after receiving a newer state revision, settle it exactly once:

```python
def _settle_pending_transition(self, raw_state: dict) -> None:
    pending = self.pending_transition
    new_revision = int(raw_state.get("state_revision", 0))
    if not pending or new_revision <= pending["before_revision"]:
        return
    reward = self.reward_calculator.transition(pending["before_state"], raw_state)
    self.experience_store.add_transition(
        self.current_run_id, pending["before_state"], pending["action_key"], reward.total,
        "in_progress", pending["policy_version"],
    )
    self._emit("transition_observed", {
        "decision_id": pending["decision_id"], "post_state": raw_state,
        "reward": {"total": reward.total, "components": reward.components,
                   "reward_version": reward.reward_version},
    })
    self.pending_transition = None
```

Run identity uses a canonical fingerprint of character, ascension, current Act, and full map node topology. Store every observed Act fingerprint as an alias in `manifest.json`; this permits restart recovery after an Act transition. A lower floor with a nonmatching fingerprint starts a new run. `GAME_OVER` computes `RewardCalculator.terminal()`, calls `ExperienceStore.finalize_run(current_run_id, result, terminal_reward.total)`, and emits `run_completed` exactly once; returning to `MAIN_MENU` after that does not emit a second terminal event.

After every successful state read, publish the full sanitized state into the dashboard snapshot before selecting a handler:

```python
self._emit("state_received", {
    "phase": "reading_state",
    "snapshot_patch": {"game_state": self.current_state_raw},
})
```

The `candidates_scored` event sets `snapshot_patch.current_decision` to the explanation, adjusted candidates, source status, and empty final action. `decision_parsed`, `fallback_selected`, `action_sent`, and `action_accepted` replace only the corresponding current-decision fields and phase.

- [ ] **Step 6: Run Agent, handler, and learning regressions**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_decision_explainer.py engine/tests/test_agent_telemetry.py engine/tests/test_handlers.py engine/tests/test_strategy.py engine/tests/test_llm_fail_closed.py -v`

Expected: all tests PASS; existing action behavior remains unchanged.

- [ ] **Step 7: Commit after explicit authorization**

```powershell
git add engine/explanation engine/main.py engine/trace engine/tests/test_decision_explainer.py engine/tests/test_agent_telemetry.py
git commit -m "feat: emit explainable agent decision telemetry"
```

---

### Task 7: Read-Only HTTP API and SSE Server

**Files:**
- Create: `engine/dashboard/__init__.py`
- Create: `engine/dashboard/server.py`
- Test: `engine/tests/test_dashboard_api.py`

**Interfaces:**
- Consumes: `DecisionEventBus` and `RunHistoryStore`.
- Produces: `DashboardServer.start()`, `stop()`, `url`, REST endpoints, and SSE.
- Consumed by: Agent startup and browser UI.

- [ ] **Step 1: Write failing API security and snapshot tests**

```python
# engine/tests/test_dashboard_api.py
import json
import threading
import urllib.error
import urllib.request

import pytest

from dashboard.server import DashboardServer
from telemetry.event_bus import DecisionEventBus


@pytest.fixture
def server(tmp_path):
    bus = DecisionEventBus()
    history = type("History", (), {
        "list_runs": lambda self, **_: [],
        "get_run": lambda self, *_args, **_kwargs: None,
        "get_decision": lambda self, *_args: None,
    })()
    instance = DashboardServer(bus, history, host="127.0.0.1", port=0)
    instance.start()
    yield instance, bus
    instance.stop()


def test_snapshot_and_get_only_contract(server):
    instance, bus = server
    bus.publish("llm_started", {"phase": "waiting_for_deepseek"}, state_revision=7)
    with urllib.request.urlopen(instance.url + "/api/snapshot") as response:
        body = json.load(response)
    assert body["phase"] == "waiting_for_deepseek"
    request = urllib.request.Request(instance.url + "/api/snapshot", method="POST", data=b"{}")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 405


def test_path_traversal_is_rejected(server):
    instance, _ = server
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(instance.url + "/api/runs/..%2F..%2Fconfig")
    assert error.value.code in {400, 404}
```

- [ ] **Step 2: Add a failing SSE reconnect test**

Open `/api/events` with header `Last-Event-ID: 1`, publish event sequence 2, and assert the stream contains:

```text
id: 2
event: telemetry
data: {"schema_version":1,"event_id":"event-2","sequence":2,"timestamp_utc":"2026-07-17T05:00:00.000Z","run_id":"run-1","battle_id":"","state_revision":9,"event_type":"state_received","payload":{}}
```

The test reads until the first blank line and closes the response, preventing an unbounded test.

- [ ] **Step 3: Verify API tests fail**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_dashboard_api.py -v`

Expected: FAIL because `DashboardServer` does not exist.

- [ ] **Step 4: Implement the threaded GET-only server**

Create a `ThreadingHTTPServer` subclass with `daemon_threads = True`. The request handler supports only:

```text
/
/styles.css
/app.js
/api/snapshot
/api/events
/api/runs?offset=<n>&limit=<n>
/api/runs/<run-id>?offset=<n>&limit=<n>
/api/runs/<run-id>/decisions/<decision-id>
```

Implement helpers with exact headers:

```python
def send_json(handler, status: int, value: object) -> None:
    body = json.dumps(value, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
```

SSE sends `retry: 1500`, uses `Last-Event-ID`, sends a heartbeat comment every 15 seconds, and exits on `BrokenPipeError`, `ConnectionResetError`, or server shutdown. Cap `limit` at 200 and reject invalid IDs before calling history methods.

- [ ] **Step 5: Run API and fault tests**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_dashboard_api.py -v`

Expected: all tests PASS; test process exits without a lingering server thread.

- [ ] **Step 6: Commit after explicit authorization**

```powershell
git add engine/dashboard engine/tests/test_dashboard_api.py
git commit -m "feat: serve read-only dashboard API and SSE"
```

---

### Task 8: Command-Center Browser Interface

**Files:**
- Create: `engine/dashboard/static/index.html`
- Create: `engine/dashboard/static/styles.css`
- Create: `engine/dashboard/static/app.js`
- Create: `engine/tests/test_dashboard_e2e.py`

**Interfaces:**
- Consumes: Task 7 REST/SSE API.
- Produces: approved A-layout Live view, History view, and Debug view.

- [ ] **Step 1: Write a failing static-contract test**

```python
# engine/tests/test_dashboard_e2e.py
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"


def test_dashboard_assets_have_required_regions_and_no_inline_model_html():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert all(marker in html for marker in (
        'id="connection-status"', 'id="combat-state"', 'id="current-decision"',
        'id="event-stream"', 'id="history-view"', 'id="debug-view"',
    ))
    assert "textContent" in js
    assert "innerHTML = event" not in js
```

- [ ] **Step 2: Verify the static-contract test fails**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_dashboard_e2e.py -v`

Expected: FAIL because the static files do not exist.

- [ ] **Step 3: Implement semantic HTML structure**

`index.html` contains:

```html
<header class="status-bar">
  <h1>Slay the Spire 2 AI</h1>
  <div id="connection-status" aria-live="polite"></div>
</header>
<nav aria-label="Dashboard views">
  <button data-view="live" aria-selected="true">实时</button>
  <button data-view="history">历史</button>
  <button data-view="debug">Debug</button>
</nav>
<main>
  <section id="live-view" class="command-grid">
    <section id="combat-state" aria-label="游戏状态"></section>
    <section id="current-decision" aria-label="当前决策"></section>
    <section id="event-stream" aria-label="实时轨迹" aria-live="polite"></section>
  </section>
  <section id="history-view" hidden></section>
  <section id="debug-view" hidden><pre id="debug-content"></pre></section>
</main>
```

Load `/styles.css` and `/app.js` with external tags. Do not place runtime JSON into HTML attributes.

- [ ] **Step 4: Implement responsive, restrained styling**

Use a three-column desktop grid `minmax(240px, .8fr) minmax(360px, 1.5fr) minmax(260px, 1fr)`, collapse to one column below `900px`, use 8px-or-smaller radii, stable minimum heights, `overflow-wrap:anywhere`, and `pre { white-space: pre-wrap; }`. Use neutral charcoal, white, amber, green, and red rather than a one-hue palette. Add visible stale, disconnected, fallback, and error states.

- [ ] **Step 5: Implement safe snapshot, SSE, history, and Debug rendering**

`app.js` must use these functions:

```javascript
const state = { snapshot: null, events: [], selectedRun: null, source: null };

function setText(node, value) {
  node.textContent = value == null ? "" : String(value);
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function loadSnapshot() {
  state.snapshot = await fetchJson("/api/snapshot");
  renderLive();
  updateStaleState();
}

function connectEvents() {
  if (state.source) state.source.close();
  state.source = new EventSource("/api/events");
  state.source.addEventListener("telemetry", (message) => {
    const event = JSON.parse(message.data);
    if (!state.events.some((item) => item.sequence === event.sequence)) {
      state.events = [...state.events, event].slice(-200);
    }
    state.snapshot = { ...(state.snapshot || {}), last_event: event,
      phase: event.payload.phase || state.snapshot?.phase,
      state_revision: event.state_revision || state.snapshot?.state_revision };
    renderLive();
    updateStaleState();
  });
  state.source.onerror = () => setText(document.querySelector("#connection-status"), "实时连接已断开，正在重连");
}

function renderLive() {
  const snapshot = state.snapshot || {};
  setText(document.querySelector("#connection-status"), snapshot.phase || "等待 Agent");
  setText(document.querySelector("#combat-state"), JSON.stringify(snapshot.game_state || {}, null, 2));
  setText(document.querySelector("#current-decision"), JSON.stringify(snapshot.current_decision || {}, null, 2));
  setText(document.querySelector("#event-stream"), state.events.slice(-30).map(
    (event) => `${event.timestamp_utc}  ${event.event_type}`
  ).join("\n"));
}

async function loadRuns() {
  const runs = await fetchJson("/api/runs?offset=0&limit=50");
  setText(document.querySelector("#history-view"), JSON.stringify(runs, null, 2));
}

async function loadRun(runId) {
  state.selectedRun = await fetchJson(`/api/runs/${encodeURIComponent(runId)}?offset=0&limit=200`);
  setText(document.querySelector("#history-view"), JSON.stringify(state.selectedRun, null, 2));
}

function renderDebug(decision) {
  setText(document.querySelector("#debug-content"), JSON.stringify(decision, null, 2));
}

function updateStaleState() {
  const node = document.querySelector("#connection-status");
  const timestamp = state.snapshot?.last_event?.timestamp_utc;
  const stale = Boolean(timestamp) && Date.now() - Date.parse(timestamp) > 3000;
  node.classList.toggle("is-stale", stale);
  if (stale) setText(node, "状态超过 3 秒未更新");
}
```

Do not assign model, Prompt, event, or state strings through `innerHTML`. Build rows with `document.createElement` and `textContent`.

- [ ] **Step 6: Run static and API tests**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_dashboard_e2e.py engine/tests/test_dashboard_api.py -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit after explicit authorization**

```powershell
git add engine/dashboard/static engine/tests/test_dashboard_e2e.py
git commit -m "feat: add live AI decision command center"
```

---

### Task 9: Configuration, Startup, and Runtime Data Hygiene

**Files:**
- Modify: `config/ai_config.yaml`
- Modify: `engine/main.py`
- Modify: `run.ps1`
- Modify: `.gitignore`
- Modify: `architecture/README.md`
- Test: `engine/tests/test_agent_telemetry.py`

**Interfaces:**
- Produces: enabled-by-default dashboard and learning configuration, CLI overrides, clean lifecycle.
- Consumed by: End-to-end verification.

- [ ] **Step 1: Add failing config and port-conflict tests**

Extend `test_agent_telemetry.py` to assert:

```python
def test_dashboard_config_defaults_are_local_and_read_only():
    import yaml
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "config" / "ai_config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert config["dashboard"] == {"enabled": True, "host": "127.0.0.1", "port": 18889}
    assert config["experience"]["enabled"] is True
    assert config["experience"]["minimum_samples"] >= 3


def test_dashboard_start_failure_does_not_stop_agent(monkeypatch):
    events = []
    agent = object.__new__(AIAgent)
    agent.dashboard = SimpleNamespace(start=lambda: (_ for _ in ()).throw(OSError("busy")))
    agent._emit = lambda event_type, payload: events.append((event_type, payload))
    assert agent._start_dashboard() is False
    assert events == [("dashboard_error", {"message": "busy"})]
```

Implement the second test with explicit `SimpleNamespace` doubles; do not open a real socket.

- [ ] **Step 2: Verify the new tests fail**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests/test_agent_telemetry.py -v`

Expected: FAIL because dashboard and experience config are absent.

- [ ] **Step 3: Add exact configuration keys**

```yaml
dashboard:
  enabled: true
  host: "127.0.0.1"
  port: 18889

experience:
  enabled: true
  data_dir: "data"
  minimum_samples: 5
  prior_weight: 10.0
  max_adjustment: 1.5
```

Add CLI arguments `--dashboard-port`, `--no-dashboard`, `--data-dir`, and `--no-experience`. CLI values override YAML. Keep all current arguments compatible.

- [ ] **Step 4: Start and stop the dashboard fail-open**

Add this helper and call it before starting the TUI:

```python
def _start_dashboard(self) -> bool:
    try:
        self.dashboard.start()
        self._emit("dashboard_started", {"url": self.dashboard.url})
        return True
    except OSError as error:
        self._emit("dashboard_error", {"message": str(error)})
        print(f"Dashboard unavailable; Agent will continue: {error}")
        return False
```

In `finally`, independently stop dashboard, flush/close history, close experience SQLite, and stop TUI.

Update `run.ps1` with optional `[int]$DashboardPort = 0` and `[switch]$NoDashboard`; append corresponding Python arguments only when provided.

- [ ] **Step 5: Ignore runtime data and visual drafts**

Append exactly:

```gitignore
# Local AI run history and experience database
data/

# Superpowers visual brainstorming artifacts
.superpowers/
```

- [ ] **Step 6: Document startup and dashboard URL**

Add to `architecture/README.md`:

```text
1. Start the game and enter a run.
2. Run .\run.ps1.
3. Open http://127.0.0.1:18889.
4. Live decisions appear under 实时; completed runs remain under 历史.
```

Also document that Debug contains full Prompts and responses but never the API key, and that DeepSeek's hosted weights are not locally retrained.

- [ ] **Step 7: Run configuration and full Python tests**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests -q`

Expected: all tests PASS with no warnings about leaked threads or unclosed SQLite connections.

- [ ] **Step 8: Commit after explicit authorization**

```powershell
git add config/ai_config.yaml engine/main.py run.ps1 .gitignore architecture/README.md engine/tests/test_agent_telemetry.py
git commit -m "feat: configure local decision dashboard"
```

---

### Task 10: Fault, Browser, and Real-Game Acceptance

**Files:**
- Modify: `engine/requirements-dev.txt`
- Modify: `engine/tests/test_dashboard_api.py`
- Modify: `engine/tests/test_dashboard_e2e.py`
- Create: `engine/tests/fixtures/dashboard_snapshot.json`
- Create: `engine/tests/fixtures/dashboard_history.json`
- Modify: `architecture/README.md`

**Interfaces:**
- Verifies every design requirement without adding a new production boundary.

- [ ] **Step 1: Add deterministic dashboard fixtures**

Create fixtures containing:

- Combat state at Act 1, floor 8, HP `40/80`.
- Two candidate sequences with scores `8.7` and `6.1`.
- One historical adjustment with sample count and confidence.
- One long Prompt, one long model response, one fallback, and one error.
- A completed loss at floor 9.

Use fictional API values only; fixtures must not contain a real key or token.

- [ ] **Step 2: Add bounded fault tests**

Test:

- Port conflict raises only from `DashboardServer.start()` and is caught by Agent startup.
- A history sink that raises does not make `DecisionEventBus.publish()` raise.
- An SSE client that disconnects leaves the server responsive to `/api/snapshot`.
- A malformed JSONL tail does not hide earlier decisions.
- `POST`, `PUT`, `PATCH`, and `DELETE` return `405`.

Every network operation must use a timeout of at most 5 seconds.

- [ ] **Step 3: Run all automated tests**

Run: `engine\venv\Scripts\python.exe -m pytest engine/tests -q`

Expected: all tests PASS.

- [ ] **Step 4: Launch the Agent in mock mode and verify HTTP manually**

Run in a resumable foreground session:

```powershell
.\run.ps1 -Mock -MockFile engine\tests\fixtures\combat_simple.json
```

Verify within 60 seconds:

```powershell
curl.exe -sS http://127.0.0.1:18889/api/snapshot
curl.exe -sS http://127.0.0.1:18889/api/runs
```

Expected: HTTP `200`, valid JSON, no key material, and at least one emitted decision lifecycle.

- [ ] **Step 5: Install Playwright verification tooling**

Append `playwright>=1.50,<2` to `engine/requirements-dev.txt`, then run:

```powershell
engine\venv\Scripts\python.exe -m pip install -r engine\requirements-dev.txt
engine\venv\Scripts\python.exe -m playwright install chromium
```

Expected: both commands exit `0`; Chromium is available to the project virtual environment.

- [ ] **Step 6: Verify desktop and narrow layouts with Playwright**

Capture screenshots at `1440x900` and `390x844`. Assert:

- `#combat-state`, `#current-decision`, and `#event-stream` are visible.
- No element has horizontal overflow beyond the viewport.
- Long Prompt and JSON remain inside `#debug-view`.
- Stale and disconnected indicators are visually distinct.
- The page reconnects after one forced SSE disconnect.

Save screenshots under a temporary ignored verification directory, not the repository.

- [ ] **Step 7: Run one real game acceptance session**

Start the game manually, enter a run, then start the Agent. Do not use Computer Use for gameplay. Monitor at intervals no greater than 60 seconds and verify:

1. Each live decision shows phase, candidates, evidence, action, and latency.
2. Terminal state closes the run and returns it from `/api/runs` after restart.
3. A second run shows at least one `experience_retrieved` event.
4. With fewer than `minimum_samples`, adjustment is zero.
5. After seeding enough fixture experiences, adjustment is visible and capped.
6. Dashboard failure does not stop game automation.

- [ ] **Step 8: Record measured acceptance evidence**

Append a dated verification section to `architecture/README.md` containing test count, dashboard URL, observed SSE latency, run ID, terminal result, history reload result, and experience-adjustment evidence. Do not include Prompt contents or secrets in the README.

- [ ] **Step 9: Commit after explicit authorization**

```powershell
git add engine/requirements-dev.txt engine/tests architecture/README.md
git commit -m "test: verify decision dashboard end to end"
```

---

## Final Verification Checklist

- [ ] `engine\venv\Scripts\python.exe -m pytest engine/tests -q` passes.
- [ ] `git diff --check` passes.
- [ ] `git status --short` shows no `data/`, `.superpowers/`, API key file, database, or screenshots.
- [ ] `curl.exe http://127.0.0.1:18889/api/snapshot` returns sanitized JSON.
- [ ] Every non-GET dashboard method returns `405`.
- [ ] SSE reconnects with `Last-Event-ID` or reloads the snapshot after a buffer gap.
- [ ] Browser layouts pass at `1440x900` and `390x844` with no overlap or horizontal overflow.
- [ ] A complete real run persists and is browsable after Agent restart.
- [ ] A later run displays retrieved historical evidence and capped score adjustment.
- [ ] Stopping the dashboard leaves the Agent's gameplay loop functional.
