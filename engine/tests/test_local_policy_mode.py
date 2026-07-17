from types import SimpleNamespace

from decisions.generic_choice import GenericChoiceHandler
from main import AIAgent
from policy.local_policy import LocalPolicy


class _NoopTui:
    def update_reasoning(self, *_args):
        pass

    def add_decision(self, *_args):
        pass

    def refresh(self):
        pass


class _Trace:
    def add_step(self, *_args):
        pass


class _EventBus:
    def __init__(self):
        self.events = []

    def publish(self, event_type, payload, **_kwargs):
        self.events.append((event_type, payload))


def _choice_state():
    return {
        "screen_type": "SHOP",
        "room_type": "SHOP",
        "decision_ready": True,
        "player": {"current_hp": 60, "max_hp": 80, "gold": 200},
        "deck": [{"name": "Strike"}, {"name": "Defend"}],
        "options": [
            {"index": 0, "kind": "map", "id": "safe", "name": "Safe Path", "enabled": True},
            {"index": 1, "kind": "map", "id": "elite", "name": "Elite Path", "enabled": True},
        ],
        "map": {
            "nodes": [
                {"id": "safe", "type": "MONSTER", "children": []},
                {"id": "elite", "type": "ELITE", "children": []},
            ],
        },
    }


def test_local_policy_mode_does_not_call_llm_for_decision():
    posted = []
    handler = GenericChoiceHandler()
    state_data = handler.extract_state(_choice_state())

    def fail_if_called(_prompt):
        raise AssertionError("DeepSeek must not make realtime decisions in local_policy mode")

    agent = object.__new__(AIAgent)
    agent.decision_mode = "local_policy"
    agent.tui = _NoopTui()
    agent.trace_logger = _Trace()
    agent.skills_registry = SimpleNamespace(get_enabled_instructions=lambda: "")
    agent.llm = SimpleNamespace(think=fail_if_called)
    agent.client = SimpleNamespace(post_decision=lambda decision: posted.append(decision) or True)

    assert agent._make_decision(SimpleNamespace(turn=0), handler, state_data) is True
    assert posted[0].type == "choose_option"
    assert posted[0].option_index == 1


def test_agent_does_not_pause_after_completed_run_by_default():
    agent = object.__new__(AIAgent)
    agent.pause_after_run_completed = False
    agent.run_completed = True
    agent.completion_pause_reported = False
    agent.event_bus = _EventBus()
    agent.current_state_raw = {"state_revision": 10}

    should_pause = agent._should_pause_after_completed_run({
        "screen_type": "MAIN_MENU",
        "in_combat": False,
    })

    assert should_pause is False
    assert agent.event_bus.events == []


def test_handle_restart_flow_singleplayer_first():
    agent = object.__new__(AIAgent)
    agent.run_completed = True
    agent.restart_flow_completed_run_id = "run-1"
    agent.restart_flow_phase = ""
    agent.current_state_raw = {"screen_type": "MAIN_MENU", "in_combat": False}

    decision = agent._handle_restart_flow({
        "options": [
            {"index": 0, "kind": "singleplayer", "name": "单人模式", "enabled": True},
            {"index": 1, "kind": "character", "name": "IRONCLAD_button", "enabled": True},
        ],
    })

    assert decision is not None
    assert decision.option_index == 0
    assert agent.restart_flow_phase == "singleplayer_selected"


def test_handle_restart_flow_ironclad_after_singleplayer():
    agent = object.__new__(AIAgent)
    agent.run_completed = True
    agent.restart_flow_completed_run_id = "run-1"
    agent.restart_flow_phase = "singleplayer_selected"
    agent.current_state_raw = {"screen_type": "MAIN_MENU", "in_combat": False}

    decision = agent._handle_restart_flow({
        "options": [
            {"index": 0, "kind": "character", "id": "SILENT_button", "name": "SILENT_button", "enabled": True},
            {"index": 1, "kind": "character", "id": "IRONCLAD_button", "name": "IRONCLAD_button", "enabled": True},
            {"index": 2, "kind": "confirm", "id": "ConfirmButton", "name": "ConfirmButton", "enabled": True},
        ],
    })

    assert decision is not None
    assert decision.option_index == 1
    assert agent.restart_flow_phase == "character_selected"


def test_handle_restart_flow_confirm_after_character():
    agent = object.__new__(AIAgent)
    agent.run_completed = True
    agent.restart_flow_completed_run_id = "run-1"
    agent.restart_flow_phase = "character_selected"
    agent.current_state_raw = {"screen_type": "MAIN_MENU", "in_combat": False}

    decision = agent._handle_restart_flow({
        "options": [
            {"index": 0, "kind": "character", "id": "IRONCLAD_button", "name": "IRONCLAD_button", "enabled": True},
            {"index": 1, "kind": "confirm", "id": "ConfirmButton", "name": "ConfirmButton", "enabled": True},
        ],
    })

    assert decision is not None
    assert decision.option_index == 1
    assert agent.restart_flow_phase == "confirming"


def test_handle_restart_flow_clears_flags_after_confirm():
    agent = object.__new__(AIAgent)
    agent.run_completed = True
    agent.restart_flow_completed_run_id = "run-1"
    agent.restart_flow_phase = "confirming"
    agent.completion_pause_reported = True
    agent.current_state_raw = {"screen_type": "MAIN_MENU", "in_combat": False}

    decision = agent._handle_restart_flow({"options": []})

    assert decision is None
    assert agent.run_completed is False
    assert agent.completion_pause_reported is False
    assert agent.restart_flow_completed_run_id == ""


def test_local_policy_avoids_previously_executed_restart_action():
    policy = LocalPolicy()
    candidates = [
        {
            "option_index": 0, "kind": "confirm", "id": "ConfirmButton",
            "name": "ConfirmButton", "score": 100, "executed_previously": True,
        },
        {"option_index": 1, "kind": "singleplayer", "id": "StandardButton", "name": "标准模式", "score": 0},
    ]
    result = policy.decide(SimpleNamespace(screen_type="CHOICE"), {"screen_type": "MAIN_MENU"}, candidates)

    assert result.decision.option_index == 1


def test_local_policy_prioritizes_unattended_start_flow_options():
    policy = LocalPolicy()
    candidates = [
        {"option_index": 0, "kind": "settings", "name": "Settings", "score": 0},
        {"option_index": 1, "kind": "singleplayer", "name": "Single Player", "score": 0},
        {"option_index": 2, "kind": "quit", "name": "Quit", "score": 0},
    ]
    result = policy.decide(SimpleNamespace(screen_type="CHOICE"), {"screen_type": "MAIN_MENU"}, candidates)

    assert result.decision.option_index == 1


def test_local_policy_prefers_standard_mode_after_singleplayer_menu_opens():
    policy = LocalPolicy()
    candidates = [
        {"option_index": 0, "kind": "singleplayer", "id": "SingleplayerButton", "name": "单人模式", "score": 0},
        {"option_index": 1, "kind": "singleplayer", "id": "MultiplayerButton", "name": "多人模式", "score": 0},
        {"option_index": 2, "kind": "singleplayer", "id": "ResetGameplayButton", "name": "重置", "score": 0},
        {"option_index": 3, "kind": "singleplayer", "id": "DisplayDropdown", "name": "显示器(1)", "score": 0},
        {"option_index": 4, "kind": "character", "id": "IRONCLAD_button", "name": "IRONCLAD_button", "score": 0},
        {"option_index": 5, "kind": "singleplayer", "id": "InviteButton", "name": "邀请", "score": 0},
        {"option_index": 6, "kind": "singleplayer", "id": "StandardButton", "name": "标准模式", "score": 0},
    ]
    result = policy.decide(SimpleNamespace(screen_type="CHOICE"), {"screen_type": "MAIN_MENU"}, candidates)

    assert result.decision.option_index == 6


def test_local_policy_confirms_run_when_confirm_button_is_available():
    policy = LocalPolicy()
    candidates = [
        {"option_index": 0, "kind": "singleplayer", "id": "StandardButton", "name": "标准模式", "score": 0},
        {"option_index": 1, "kind": "character", "id": "IRONCLAD_button", "name": "IRONCLAD_button", "score": 0},
        {"option_index": 2, "kind": "confirm", "id": "ConfirmButton", "name": "ConfirmButton", "score": 0},
    ]
    result = policy.decide(SimpleNamespace(screen_type="CHOICE"), {"screen_type": "MAIN_MENU"}, candidates)

    assert result.decision.option_index == 2


def test_local_policy_prefers_ironclad_for_unattended_runs():
    policy = LocalPolicy()
    candidates = [
        {"option_index": 1, "kind": "character", "id": "IRONCLAD_button", "name": "IRONCLAD_button", "score": 0},
        {"option_index": 2, "kind": "character", "id": "SILENT_button", "name": "SILENT_button", "score": 0},
        {"option_index": 3, "kind": "character", "id": "REGENT_button", "name": "REGENT_button", "score": 10},
        {"option_index": 4, "kind": "character", "id": "NECROBINDER_button", "name": "NECROBINDER_button", "score": 0},
    ]
    result = policy.decide(SimpleNamespace(screen_type="CHOICE"), {"screen_type": "MAIN_MENU"}, candidates)

    assert result.decision.option_index == 1


def test_local_policy_continues_existing_run_before_clicking_character_controls():
    policy = LocalPolicy()
    candidates = [
        {"option_index": 0, "kind": "continue_run", "id": "continue", "name": "Continue run", "score": 0},
        {"option_index": 1, "kind": "character", "id": "IRONCLAD_button", "name": "IRONCLAD_button", "score": 0},
        {"option_index": 6, "kind": "character", "id": "CharSelectButton", "name": "CharSelectButton", "score": 0},
    ]
    result = policy.decide(SimpleNamespace(screen_type="CHOICE"), {"screen_type": "MAIN_MENU"}, candidates)

    assert result.decision.option_index == 0


def test_choice_candidates_keep_option_metadata_for_start_flow():
    handler = GenericChoiceHandler()
    state_data = handler.extract_state({
        "screen_type": "MAIN_MENU",
        "decision_ready": True,
        "player": {},
        "deck": [],
        "options": [
            {"index": 0, "kind": "settings", "name": "Settings", "enabled": True},
            {"index": 1, "kind": "singleplayer", "name": "Single Player", "enabled": True},
        ],
    })

    from explanation.decision_explainer import normalized_candidates
    candidates = normalized_candidates("CHOICE", state_data)

    assert candidates[1]["kind"] == "singleplayer"
    assert candidates[1]["name"] == "Single Player"
