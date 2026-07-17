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

    def publish(
        self,
        event_type: str,
        payload: dict,
        *,
        run_id: str = "",
        battle_id: str = "",
        state_revision: int = 0,
    ) -> TelemetryEvent:
        clean = redact_secrets(payload, self._secret_values)
        with self._condition:
            self._sequence += 1
            event = TelemetryEvent.create(
                sequence=self._sequence,
                event_type=event_type,
                run_id=run_id,
                battle_id=battle_id,
                state_revision=state_revision,
                payload=clean,
            )
            self._events.append(event)
            patch = clean.get("snapshot_patch", {})
            if isinstance(patch, dict):
                self._snapshot.update(deepcopy(patch))
            self._snapshot.update(
                {
                    "phase": clean.get("phase", self._snapshot["phase"]),
                    "state_revision": state_revision or self._snapshot["state_revision"],
                    "last_event": event.to_dict(),
                }
            )
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
