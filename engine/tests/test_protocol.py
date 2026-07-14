"""测试 Decision 协议 — 所有决策类型的构造、序列化、输出格式。"""

from communication.protocol import Decision


class TestDecisionPlayCard:
    def test_play_card(self):
        d = Decision.play_card(0, 1)
        assert d.type == "play_card"
        assert d.hand_index == 0
        assert d.monster_index == 1
        assert d.to_json() == {"type": "play_card", "hand_index": 0, "monster_index": 1}
        assert d.to_llm_format() == "PLAY 0 1"

    def test_play_card_no_target(self):
        d = Decision.play_card(2)
        assert d.to_llm_format() == "PLAY 2 0"


class TestDecisionEndTurn:
    def test_end_turn(self):
        d = Decision.end_turn()
        assert d.type == "end_turn"
        assert d.to_json() == {"type": "end_turn"}
        assert d.to_llm_format() == "END"


class TestDecisionPotion:
    def test_use_potion(self):
        d = Decision.use_potion(1, 0)
        assert d.type == "use_potion"
        assert d.potion_slot == 1
        assert d.to_json() == {"type": "use_potion", "potion_slot": 1, "monster_index": 0}
        assert d.to_llm_format() == "POTION 1 0"


class TestDecisionPickCard:
    def test_pick_card(self):
        d = Decision.pick_card(2)
        assert d.type == "pick_card"
        assert d.card_index == 2
        assert d.to_json() == {"type": "pick_card", "card_index": 2}
        assert d.to_llm_format() == "PICK 2"

    def test_skip_reward(self):
        d = Decision.skip_reward()
        assert d.type == "pick_card"
        assert d.card_index == -1
        assert d.to_json() == {"type": "pick_card", "card_index": -1}
        assert d.to_llm_format() == "SKIP"


class TestDecisionRestSmith:
    def test_rest(self):
        d = Decision.rest()
        assert d.type == "rest"
        assert d.to_json() == {"type": "rest"}
        assert d.to_llm_format() == "REST"

    def test_smith(self):
        d = Decision.smith(0)
        assert d.type == "smith"
        assert d.card_index == 0
        assert d.to_json() == {"type": "smith", "card_index": 0}
        assert d.to_llm_format() == "SMITH 0"


class TestDecisionEvent:
    def test_choose_option(self):
        d = Decision.choose_option(1)
        assert d.type == "choose_option"
        assert d.option_index == 1
        assert d.to_json() == {"type": "choose_option", "option_index": 1}
        assert d.to_llm_format() == "CHOOSE 1"


class TestDecisionRepr:
    def test_repr(self):
        assert repr(Decision.play_card(0, 1)) == "PLAY 0 1"
        assert repr(Decision.end_turn()) == "END"
        assert repr(Decision.pick_card(0)) == "PICK 0"
        assert repr(Decision.rest()) == "REST"
