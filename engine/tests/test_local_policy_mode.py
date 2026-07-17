from types import SimpleNamespace

from decisions.generic_choice import GenericChoiceHandler
from main import AIAgent


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
