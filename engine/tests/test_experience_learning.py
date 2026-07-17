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
    store.finalize_run("run-1", "victory", terminal_reward=200.0)
    adjusted = service.apply(context(), candidates)[0]
    assert 4.0 < adjusted["final_score"] <= 5.5
    assert adjusted["sample_count"] == 3
    store.close()
