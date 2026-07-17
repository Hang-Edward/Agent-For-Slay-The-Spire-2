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
