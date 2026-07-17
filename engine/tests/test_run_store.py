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
    assert not store.worker.is_alive()


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
