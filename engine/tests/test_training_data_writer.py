import json

from learning.training_data_writer import TrainingDataWriter
from telemetry.events import TelemetryEvent


def event(sequence, event_type, run_id="run-1", payload=None):
    return TelemetryEvent.create(
        sequence=sequence,
        event_type=event_type,
        run_id=run_id,
        payload=payload or {},
        timestamp_utc=f"2026-07-18T00:00:0{sequence}.000Z",
    )


def test_training_writer_persists_transition_and_teacher_review(tmp_path):
    writer = TrainingDataWriter(tmp_path)
    writer.enqueue(event(1, "decision_parsed", payload={
        "decision_id": "d1",
        "source": "policy",
        "command": "PLAY 0 0",
        "action": {"type": "play_card", "hand_index": 0, "monster_index": 0},
        "pre_state": {"screen_type": "COMBAT", "player": {"current_hp": 50}},
        "candidates": [{"action_key": "cards:0", "final_score": 12.0}],
    }))
    writer.enqueue(event(2, "transition_observed", payload={
        "decision_id": "d1",
        "reward": {"total": 3.5, "components": {"enemy_hp_delta": 3.5}},
    }))
    writer.enqueue(event(3, "run_completed", payload={
        "result": "victory",
        "floor": 50,
        "terminal_reward": 175.0,
    }))
    writer.enqueue(event(4, "teacher_review_finished", payload={
        "status": "reviewed",
        "review": "Prefer lethal when safe.",
    }))
    writer.flush()

    run_dir = tmp_path / "training" / "runs" / "run-1"
    transition = json.loads((run_dir / "transitions.jsonl").read_text(encoding="utf-8").splitlines()[0])
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    review = json.loads((run_dir / "teacher_review.json").read_text(encoding="utf-8"))

    assert transition["decision_id"] == "d1"
    assert transition["chosen_action"]["type"] == "play_card"
    assert transition["reward"]["total"] == 3.5
    assert transition["pre_state"]["screen_type"] == "COMBAT"
    assert summary["result"] == "victory"
    assert review["review"] == "Prefer lethal when safe."
    writer.close()
