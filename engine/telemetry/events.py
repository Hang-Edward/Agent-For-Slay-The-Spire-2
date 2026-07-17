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
    # 统一输出毫秒精度的 UTC 时间，保证事件信封格式稳定。
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
