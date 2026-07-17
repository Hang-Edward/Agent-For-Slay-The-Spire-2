"""通用非战斗选择协议测试。"""

import pytest
import time
from types import SimpleNamespace

from decisions.generic_choice import GenericChoiceHandler
from decisions.registry import DecisionRegistry
from main import AIAgent
from llm.dryrun_client import DryRunClient
from llm.response_parser import InvalidDecisionError
from state.game_state import GameState


def choice_state(options=None):
    return {
        "screen_type": "SHOP",
        "room_type": "SHOP",
        "decision_ready": True,
        "player": {"current_hp": 50, "max_hp": 80, "gold": 100},
        "deck": [{"name": "Strike"}, {"name": "Strike"}, {"name": "Defend"}],
        "options": options or [
            {"index": 0, "kind": "buy", "name": "Card", "cost": 60, "enabled": True},
            {"index": 1, "kind": "buy", "name": "Relic", "cost": 150, "enabled": False},
        ],
    }


def test_registry_prefers_live_options_protocol():
    handler = DecisionRegistry().get_handler_for_state(choice_state())
    assert isinstance(handler, GenericChoiceHandler)


def test_prompt_contains_run_context_and_availability():
    handler = GenericChoiceHandler()
    prompt = handler.build_prompt(handler.extract_state(choice_state()))
    assert "HP: 50/80 | Gold: 100" in prompt
    assert "Strike x2" in prompt
    assert "[0] [AVAILABLE]" in prompt
    assert "[1] [DISABLED]" in prompt


def test_parse_only_accepts_enabled_index():
    handler = GenericChoiceHandler()
    state = handler.extract_state(choice_state())
    assert handler.parse_response("CHOOSE 0", state).option_index == 0
    with pytest.raises(InvalidDecisionError, match="unavailable"):
        handler.parse_response("CHOOSE 1", state)


def test_parse_rejects_explanatory_last_line():
    handler = GenericChoiceHandler()
    state = handler.extract_state(choice_state())
    with pytest.raises(InvalidDecisionError, match="unrecognized"):
        handler.parse_response("I prefer the card.\nPlease choose 0.", state)


def test_single_enabled_option_is_automatic():
    handler = GenericChoiceHandler()
    state = handler.extract_state(choice_state())
    assert handler.try_auto_decision(state).option_index == 0


def test_selected_card_is_confirmed_automatically():
    raw = choice_state([
        {"index": 0, "kind": "card", "name": "Strike", "enabled": True, "selected": True},
        {"index": 1, "kind": "card", "name": "Defend", "enabled": True, "selected": False},
        {"index": 2, "kind": "confirm", "name": "Confirm", "enabled": True},
    ])
    raw["screen_type"] = "CARD_SELECT_UPGRADE"
    handler = GenericChoiceHandler()
    state = handler.extract_state(raw)

    assert handler.try_auto_decision(state).option_index == 2


def test_prompt_marks_selected_card():
    raw = choice_state([
        {"index": 0, "kind": "card", "name": "Strike", "enabled": True, "selected": True},
        {"index": 1, "kind": "confirm", "name": "Confirm", "enabled": True},
    ])
    raw["screen_type"] = "CARD_SELECT_UPGRADE"
    handler = GenericChoiceHandler()

    prompt = handler.build_prompt(handler.extract_state(raw))

    assert "[0] [SELECTED]" in prompt


def test_fallback_avoids_a_previously_stalled_option():
    handler = GenericChoiceHandler()
    state = handler.extract_state(choice_state([
        {"index": 0, "kind": "event", "name": "First", "enabled": True},
        {"index": 1, "kind": "event", "name": "Second", "enabled": True},
    ]))
    state["stalled_option_indices"] = [0]

    assert handler.fallback_decision(state).option_index == 1


def test_dryrun_chooses_first_available_option():
    client = DryRunClient()
    response, _ = client.think("[3] [DISABLED] X\n[4] [AVAILABLE] Y\nCHOOSE <index>")
    assert response == "CHOOSE 4"


def test_game_state_exposes_complete_choice_context():
    raw = choice_state()
    state = GameState.from_json(raw)
    assert state.room_type == "SHOP"
    assert [card.name for card in state.deck] == ["Strike", "Strike", "Defend"]
    assert state.options[0]["kind"] == "buy"


class _NoopTui:
    def update_state(self, *_args):
        pass

    def update_reasoning(self, *_args):
        pass

    def add_decision(self, *_args):
        pass

    def refresh(self):
        pass

    def set_status(self, *_args, **_kwargs):
        pass


class _Trace:
    def add_step(self, *_args):
        pass


def test_rejected_auto_action_is_reported_for_retry():
    agent = object.__new__(AIAgent)
    agent.tui = _NoopTui()
    agent.trace_logger = _Trace()
    agent.skills_registry = SimpleNamespace(
        get_enabled_instructions=lambda: "",
        enabled_skills=[],
    )
    agent.client = SimpleNamespace(post_decision=lambda _decision: False)
    handler = GenericChoiceHandler()
    state_data = handler.extract_state(choice_state())

    assert agent._make_decision(SimpleNamespace(turn=0), handler, state_data) is False


def test_invalid_model_output_executes_safe_fallback():
    posted = []
    agent = object.__new__(AIAgent)
    agent.tui = _NoopTui()
    agent.trace_logger = _Trace()
    agent.skills_registry = SimpleNamespace(
        get_enabled_instructions=lambda: "",
        enabled_skills=[],
    )
    agent.llm = SimpleNamespace(think=lambda _prompt: ("not an action", 0.01))
    agent.client = SimpleNamespace(post_decision=lambda decision: posted.append(decision) or True)
    handler = GenericChoiceHandler()
    state_data = handler.extract_state(choice_state([
        {"index": 2, "kind": "event", "name": "First", "enabled": True},
        {"index": 3, "kind": "event", "name": "Second", "enabled": True},
    ]))

    assert agent._make_decision(SimpleNamespace(turn=0), handler, state_data) is True
    assert posted[0].type == "choose_option"
    assert posted[0].option_index == 2


def test_prompt_marks_stalled_option_when_alternative_exists():
    handler = GenericChoiceHandler()
    state = handler.extract_state(choice_state([
        {"index": 0, "kind": "event", "name": "First", "enabled": True},
        {"index": 1, "kind": "event", "name": "Second", "enabled": True},
    ]))
    state["stalled_option_indices"] = [0]
    prompt = handler.build_prompt(state)
    assert "[0] [STALLED_PREVIOUSLY]" in prompt
    assert "[1] [AVAILABLE]" in prompt


def test_same_ready_state_is_retried_after_stall(monkeypatch):
    raw = choice_state([
        {"index": 0, "kind": "event", "name": "First", "enabled": True},
        {"index": 1, "kind": "event", "name": "Second", "enabled": True},
    ])
    state = GameState.from_json(raw)
    agent = object.__new__(AIAgent)
    agent.client = SimpleNamespace(get_state=lambda: state)
    agent.registry = DecisionRegistry()
    agent.tui = _NoopTui()
    agent.llm = SimpleNamespace(name="test")
    agent.current_state_raw = None
    handler = agent.registry.get_handler_for_state(raw)
    state_data = handler.extract_state(raw)
    screen_id = agent._compute_screen_id(handler.screen_type, state_data)
    agent.last_screen_id = screen_id
    agent.last_action_time = time.monotonic() - 13
    agent.last_decision = SimpleNamespace(type="choose_option", option_index=0)
    agent.stalled_options = {}
    agent.decision_failure_count = 0
    agent.next_decision_time = 0.0
    captured = {}
    agent._make_decision = lambda _state, _handler, data: captured.update(data) or False
    monkeypatch.setattr("main.time.sleep", lambda _seconds: None)

    agent._run_iteration()

    assert captured["stalled_option_indices"] == [0]
    assert agent.last_screen_id == ""
    assert agent.decision_failure_count == 1
    assert agent.next_decision_time > time.monotonic()
