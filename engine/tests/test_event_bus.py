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
    bus.publish(
        "state_received",
        {
            "phase": "reading_state",
            "snapshot_patch": {"game_state": {"floor": 8}},
        },
        state_revision=8,
    )
    bus.publish(
        "llm_started",
        {
            "phase": "waiting_for_deepseek",
            "snapshot_patch": {"current_decision": {"status": "thinking"}},
        },
        state_revision=8,
    )
    snapshot = bus.snapshot()
    assert snapshot["phase"] == "waiting_for_deepseek"
    assert snapshot["state_revision"] == 8
    assert snapshot["game_state"]["floor"] == 8
    assert snapshot["current_decision"]["status"] == "thinking"
