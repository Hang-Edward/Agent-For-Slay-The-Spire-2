"""整回合、卡组、路线与多人协作策略测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from decisions.combat import CombatHandler
from decisions.registry import get_default_registry
from main import AIAgent
from state.game_state import Card, GameState, Monster, Teammate
from strategy.combat_planner import analyze_turn
from strategy.deck_evaluator import analyze_deck, evaluate_card
from strategy.route_planner import score_map_options
from strategy.team_coordinator import TeamCoordinator
from skills.loader import load_skills_from_config


def card(name, card_type="ATTACK", cost=1, damage=0, block=0, description=""):
    return Card(name, name, name, cost, cost, card_type, "COMMON", "", False,
                True, "", 0, damage, block, 0, False, False, description)


def state(hand=None, hp=50, block=0, energy=3, teammates=None):
    return GameState(
        screen_type="COMBAT", in_combat=True, player_hp=hp, player_max_hp=80,
        player_block=block, player_energy=energy, player_energy_this_turn=energy,
        player_powers=[], monsters=[Monster("m", "Enemy", 30, 30, 0, "ATTACK", 20, 1,
                                            False, False, True, 0)],
        hand=hand or [], draw_pile_count=0, discard_pile=[], exhaust_pile=[],
        relics=[], potions=[], turn=1, act=1, floor=1, ascension_level=0,
        char_class="IRONCLAD", teammates=teammates or [],
    )


def test_turn_planner_values_block_under_high_risk():
    plan = analyze_turn(state([
        card("Strike", damage=6),
        card("Defend", card_type="SKILL", block=8),
        card("Big Defend", card_type="SKILL", cost=2, block=16),
    ], hp=25))
    assert plan["risk"] == "HIGH"
    assert plan["candidate_sequences"][0]["estimated_hp_loss"] < 20


def test_turn_planner_enumerates_whole_turn_sequences():
    plan = analyze_turn(state([card("A", damage=6), card("B", damage=7), card("C", damage=8)]))
    assert any(candidate["cards"] == [0, 1, 2] for candidate in plan["candidate_sequences"])


def test_turn_planner_credits_killing_attacker():
    combat = state([card("Heavy", cost=2, damage=35)], hp=25, energy=2)
    plan = analyze_turn(combat)
    candidate = plan["candidate_sequences"][0]
    assert candidate["damage_avoided_by_kills"] == 20
    assert candidate["estimated_hp_loss"] == 0


def test_single_playable_card_still_uses_strategy_model():
    combat = state([card("Painful Attack", damage=1, description="Lose HP")])
    handler = CombatHandler()
    assert handler.try_auto_decision({"game_state": combat, "playable_cards": [(0, combat.hand[0])]}) is None


def test_combat_prompt_contains_plan_and_team_history():
    teammate = Teammate("2", "SILENT", 50, 70, 3, 0, 0, 1, "None", True)
    combat = state([card("Strike", damage=6)], teammates=[teammate])
    combat.team_actions = [{"actor": "SILENT", "description": "SILENT played Vulnerable", "is_local": False}]
    handler = CombatHandler()
    prompt = handler.build_prompt({"game_state": combat, "turn_plan": analyze_turn(combat)})
    assert "Whole-turn risk budget" in prompt
    assert "Teammate actions this turn" in prompt
    assert "SILENT played Vulnerable" in prompt


def test_deck_profile_and_candidate_fit():
    deck = [card(f"Attack{i}", damage=6) for i in range(8)] + [card("Defend", "SKILL", block=5)]
    profile = analyze_deck(deck)
    evaluation = evaluate_card(card("Block Engine", "SKILL", block=12), profile)
    assert "block" in profile["needs"]
    assert evaluation["score"] >= 2


def test_route_scoring_prefers_shop_when_rich():
    graph = {"nodes": [
        {"id": "1:0", "type": "SHOP", "children": ["2:0"]},
        {"id": "1:1", "type": "MONSTER", "children": ["2:1"]},
        {"id": "2:0", "type": "REST_SITE", "children": []},
        {"id": "2:1", "type": "MONSTER", "children": []},
    ]}
    options = [
        {"index": 0, "id": "1:0", "kind": "map", "enabled": True},
        {"index": 1, "id": "1:1", "kind": "map", "enabled": True},
    ]
    scores = score_map_options(graph, options, hp=60, max_hp=80, gold=250)
    assert scores[0]["option_index"] == 0


def test_route_scoring_prefers_safer_path_at_low_hp():
    graph = {"nodes": [
        {"id": "1:0", "type": "EVENT", "children": ["2:0"]},
        {"id": "1:1", "type": "MONSTER", "children": ["2:1"]},
        {"id": "2:0", "type": "REST_SITE", "children": []},
        {"id": "2:1", "type": "ELITE", "children": []},
    ]}
    options = [
        {"index": 0, "id": "1:0", "kind": "map", "enabled": True},
        {"index": 1, "id": "1:1", "kind": "map", "enabled": True},
    ]
    scores = score_map_options(graph, options, hp=20, max_hp=80, gold=20)
    assert scores[0]["option_index"] == 0


def test_team_coordinator_waits_then_times_out(monkeypatch):
    teammate = Teammate("2", "SILENT", 50, 70, 0, 2, 4, 1, "Play", True)
    coordinator = TeamCoordinator(enabled=True, timeout_seconds=10)
    clock = iter([100.0, 105.0, 111.0])
    monkeypatch.setattr("strategy.team_coordinator.time.monotonic", lambda: next(clock))
    combat = state(teammates=[teammate])
    assert coordinator.should_wait(combat)[0] is True
    assert coordinator.should_wait(combat)[0] is True
    assert coordinator.should_wait(combat)[0] is False


def test_team_coordinator_releases_when_teammate_ends():
    teammate = Teammate("2", "SILENT", 50, 70, 0, 0, 0, 1, "None", True)
    assert TeamCoordinator().should_wait(state(teammates=[teammate]))[0] is False


class _Tui:
    def update_state(self, *_args): pass
    def update_reasoning(self, *_args): pass
    def set_status(self, *_args, **_kwargs): pass
    def refresh(self): pass


def test_agent_does_not_act_while_waiting_for_teammate(monkeypatch):
    raw = {
        "screen_type": "COMBAT", "in_combat": True, "decision_ready": True,
        "state_revision": 1, "turn": 1, "act": 1, "floor": 1,
        "player": {"current_hp": 50, "max_hp": 80, "energy": 3, "phase": "Play"},
        "monsters": [{"id": "m", "name": "Enemy", "current_hp": 20, "max_hp": 20,
                      "intent": "ATTACK", "intent_damage": 5, "intent_hits": 1,
                      "targetable": True, "target_index": 0}],
        "hand": [{"uuid": "c", "id": "Strike", "name": "Strike", "cost": 1,
                  "cost_for_turn": 1, "type": "ATTACK", "damage": 6, "is_playable": True,
                  "has_target": True}],
        "teammates": [{"net_id": "2", "character": "SILENT", "current_hp": 50,
                       "max_hp": 70, "energy": 2, "hand_count": 3, "turn": 1,
                       "phase": "Play", "is_alive": True}],
    }
    combat = GameState.from_json(raw)
    agent = object.__new__(AIAgent)
    agent.client = SimpleNamespace(get_state=lambda: combat)
    agent.registry = get_default_registry()
    agent.tui = _Tui()
    agent.llm = SimpleNamespace(name="test")
    agent.team_coordinator = SimpleNamespace(should_wait=lambda _state: (True, "waiting"))
    agent.current_state_raw = None
    agent.last_screen_id = ""
    agent.last_action_time = 0.0
    agent.last_decision = None
    agent.stalled_options = {}
    agent.decision_failure_count = 0
    agent.next_decision_time = 0.0
    agent._make_decision = lambda *_args: (_ for _ in ()).throw(AssertionError("must wait"))
    monkeypatch.setattr("main.time.sleep", lambda _seconds: None)

    agent._run_iteration()


def test_real_config_enables_adaptive_strategy():
    config_path = Path(__file__).resolve().parents[2] / "config" / "ai_config.yaml"
    registry = load_skills_from_config(str(config_path))
    enabled = {skill.id for skill in registry.enabled_skills}
    assert {"adaptive_hp_trade", "deck_coherence", "adaptive_pathing", "team_coordination"} <= enabled
