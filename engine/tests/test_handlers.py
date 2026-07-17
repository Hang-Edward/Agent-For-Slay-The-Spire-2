"""测试所有决策处理器 — extract_state, build_prompt, parse_response, should_act, try_auto_decision。"""

import copy
import json
import os

import pytest

from decisions.registry import get_default_registry
from llm.response_parser import InvalidDecisionError, parse_llm_response

# ─── Fixture 路径 ──────────────────────────────────────────
FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name):
    path = os.path.join(FIXTURE_DIR, name)
    with open(path) as f:
        return json.load(f)


# ─── Combat Handler ────────────────────────────────────────

class TestCombatHandler:
    def setup_method(self):
        self.reg = get_default_registry()
        self.raw = load_fixture("combat_simple.json")
        self.handler = self.reg.get_handler_for_state(self.raw)
        assert self.handler is not None
        assert self.handler.screen_type == "COMBAT"

    def test_extract_state(self):
        sd = self.handler.extract_state(self.raw)
        assert sd["has_playable_cards"] is True
        assert sd["has_alive_monsters"] is True
        assert len(sd["playable_cards"]) > 0

    def test_build_prompt(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd)
        assert "Jaw Worm" in prompt
        assert "Strike" in prompt
        assert "Defend" in prompt
        assert "Bash" in prompt
        assert "PLAY" in prompt or "PLAY" in prompt

    def test_build_prompt_with_strategy(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd, "Prioritize block cards.")
        assert "Prioritize block" in prompt

    def test_parse_play(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("PLAY 0 0", sd)
        assert d.type == "play_card"
        assert d.hand_index == 0

    def test_parse_end(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("END", sd)
        assert d.type == "end_turn"

    def test_should_act_true(self):
        sd = self.handler.extract_state(self.raw)
        assert self.handler.should_act(sd) is True

    def test_auto_decision_single_card(self):
        # combat_simple has 3 playable cards, so auto should not fire
        sd = self.handler.extract_state(self.raw)
        assert self.handler.try_auto_decision(sd) is None

    def test_should_act_no_monsters(self):
        raw = dict(self.raw)
        raw["monsters"] = []
        sd = self.handler.extract_state(raw)
        assert self.handler.should_act(sd) is False

    def test_no_playable_cards_auto_end_turn(self):
        raw = copy.deepcopy(self.raw)
        raw["player"]["energy"] = 0
        for card in raw["hand"]:
            card["is_playable"] = False
            card["playable_reason"] = "EnergyCostTooHigh"
        sd = self.handler.extract_state(raw)
        assert self.handler.should_act(sd) is True
        assert self.handler.try_auto_decision(sd).type == "end_turn"

    def test_fallback_chooses_a_playable_card_and_valid_target(self):
        raw = copy.deepcopy(self.raw)
        raw["hand"][0]["is_playable"] = False
        raw["hand"][0]["playable_reason"] = "BlockedByStatus"
        sd = self.handler.extract_state(raw)

        decision = self.handler.fallback_decision(sd)

        assert decision.type == "play_card"
        assert decision.hand_index != 0
        assert raw["hand"][decision.hand_index]["is_playable"] is True
        assert decision.monster_index == 0

    def test_waits_while_mod_action_is_not_ready(self):
        raw = copy.deepcopy(self.raw)
        raw["decision_ready"] = False
        sd = self.handler.extract_state(raw)
        assert self.handler.should_act(sd) is False

    def test_rejects_out_of_range_card(self):
        sd = self.handler.extract_state(self.raw)
        with pytest.raises(InvalidDecisionError):
            self.handler.parse_response("PLAY 99 0", sd)

    def test_rejects_invalid_monster_target(self):
        sd = self.handler.extract_state(self.raw)
        with pytest.raises(InvalidDecisionError):
            self.handler.parse_response("PLAY 0 99", sd)

    def test_validates_usable_potion_slot(self):
        raw = copy.deepcopy(self.raw)
        raw["potions"] = [{
            "slot": 1,
            "name": "Fire Potion",
            "target_type": "AnyEnemy",
            "can_use": True,
        }]
        sd = self.handler.extract_state(raw)
        assert self.handler.parse_response("POTION 1 0", sd).potion_slot == 1
        with pytest.raises(InvalidDecisionError):
            self.handler.parse_response("POTION 2 0", sd)

    def test_parser_uses_only_last_line_and_never_defaults(self):
        assert parse_llm_response("I considered END.\nPLAY 0 0").type == "play_card"
        with pytest.raises(InvalidDecisionError):
            parse_llm_response("I cannot decide")
        with pytest.raises(InvalidDecisionError):
            parse_llm_response("")


class TestCombatHandlerBlockTest:
    """防御测试场景 — Lagavulin 高伤害+有格挡牌。"""

    def setup_method(self):
        self.reg = get_default_registry()
        self.raw = load_fixture("combat_block_test.json")
        self.handler = self.reg.get_handler_for_state(self.raw)

    def test_extract_state(self):
        sd = self.handler.extract_state(self.raw)
        assert sd["has_playable_cards"]
        # 检查是否有多种选择（Strike vs Defend vs Bash）
        assert len(sd["playable_cards"]) >= 3

    def test_prompt_contains_lagavulin(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd)
        assert "Lagavulin" in prompt

    def test_coT_in_prompt(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd)
        assert "whole remaining turn" in prompt
        assert "no explanation" in prompt


# ─── Card Reward Handler ───────────────────────────────────

class TestCardRewardHandler:
    def setup_method(self):
        self.reg = get_default_registry()
        self.raw = load_fixture("card_reward.json")
        self.handler = self.reg.get_handler_for_state(self.raw)
        assert self.handler is not None

    def test_screen_type(self):
        assert self.handler.screen_type == "CARD_REWARD"

    def test_extract_state(self):
        sd = self.handler.extract_state(self.raw)
        assert len(sd["cards"]) == 3
        assert sd["can_skip"] is True
        assert sd["total_cards"] > 0
        assert sd["player_hp"] == 47

    def test_build_prompt(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd)
        assert "Heavy Blade" in prompt
        assert "Shrug It Off" in prompt
        assert "Metallicize" in prompt
        assert "PICK" in prompt

    def test_build_prompt_with_strategy(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd, "Prioritize block cards.")
        assert "Prioritize block" in prompt

    def test_coT_in_prompt(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd)
        assert "Think step by step" in prompt

    def test_parse_pick(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("PICK 0", sd)
        assert d.type == "pick_card"
        assert d.card_index == 0

    def test_parse_pick_second(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("PICK 1", sd)
        assert d.card_index == 1

    def test_parse_skip(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("SKIP", sd)
        assert d.card_index == -1

    def test_parse_invalid_index_default_skip(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("PICK 99", sd)
        assert d.card_index == -1  # 越界则跳过

    def test_boss_reward_alias(self):
        raw = dict(self.raw)
        raw["screen_type"] = "BOSS_REWARD"
        handler = self.reg.get_handler_for_state(raw)
        assert handler is not None


# ─── Rest Site Handler ─────────────────────────────────────

class TestRestSiteHandler:
    def setup_method(self):
        self.reg = get_default_registry()
        self.raw = load_fixture("rest_site.json")
        self.handler = self.reg.get_handler_for_state(self.raw)
        assert self.handler is not None

    def test_screen_type(self):
        assert self.handler.screen_type == "REST"

    def test_extract_state(self):
        sd = self.handler.extract_state(self.raw)
        assert sd["has_rest"] is True
        assert sd["has_smith"] is True
        assert sd["heal_amount"] == 18
        assert sd["player_hp"] == 30

    def test_build_prompt(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd)
        assert "REST" in prompt
        assert "SMITH" in prompt

    def test_coT_in_prompt(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd)
        assert "Think step by step" in prompt

    def test_parse_rest(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("REST", sd)
        assert d.type == "rest"

    def test_parse_smith(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("SMITH 1", sd)
        assert d.type == "smith"
        assert d.card_index == 1

    def test_parse_default_rest(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("some random text", sd)
        assert d.type == "rest"  # 默认休息


# ─── Event Handler ─────────────────────────────────────────

class TestEventHandler:
    def setup_method(self):
        self.reg = get_default_registry()
        self.raw = load_fixture("event.json")
        self.handler = self.reg.get_handler_for_state(self.raw)
        assert self.handler is not None

    def test_screen_type(self):
        assert self.handler.screen_type == "EVENT"

    def test_extract_state(self):
        sd = self.handler.extract_state(self.raw)
        assert sd["event_name"] == "Big Fish"
        assert len(sd["options"]) == 3
        assert sd["options"][0]["label"] == "Gain sustenance"

    def test_build_prompt(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd)
        assert "Big Fish" in prompt
        assert "CHOOSE" in prompt

    def test_coT_in_prompt(self):
        sd = self.handler.extract_state(self.raw)
        prompt = self.handler.build_prompt(sd)
        assert "Think step by step" in prompt

    def test_parse_choose(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("CHOOSE 2", sd)
        assert d.type == "choose_option"
        assert d.option_index == 2

    def test_parse_default_first_option(self):
        sd = self.handler.extract_state(self.raw)
        d = self.handler.parse_response("random text", sd)
        assert d.option_index == 0  # 默认选第一个


# ─── Registry Tests ────────────────────────────────────────

class TestRegistry:
    def setup_method(self):
        self.reg = get_default_registry()

    def test_all_screens_registered(self):
        screens = self.reg.supported_screens
        assert "COMBAT" in screens
        assert "CARD_REWARD" in screens
        assert "BOSS_REWARD" in screens
        assert "REST" in screens
        assert "EVENT" in screens

    def test_each_handler_is_singleton(self):
        """同一屏幕类型返回相同的处理器实例。"""
        h1 = self.reg.get_handler("COMBAT")
        h2 = self.reg.get_handler("COMBAT")
        assert h1 is h2

    def test_unknown_screen_returns_none(self):
        assert self.reg.get_handler("UNKNOWN_SCREEN") is None
