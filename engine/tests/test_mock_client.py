"""测试 MockModClient — fixture 加载、状态读取、序列模式。"""

import os

from tests.mock_mod_client import MockModClient
from communication.protocol import Decision

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class TestMockModClient:
    def setup_method(self):
        self.client = MockModClient()

    def test_load_fixture(self):
        path = os.path.join(FIXTURE_DIR, "combat_simple.json")
        ok = self.client.load_fixture(path)
        assert ok is True

    def test_get_state(self):
        path = os.path.join(FIXTURE_DIR, "combat_simple.json")
        self.client.load_fixture(path)
        state = self.client.get_state()
        assert state is not None
        assert state.in_combat is True
        assert len(state.hand) == 3

    def test_get_status(self):
        path = os.path.join(FIXTURE_DIR, "card_reward.json")
        self.client.load_fixture(path)
        status = self.client.get_status()
        assert status["in_game"] is True
        assert status["in_battle"] is False  # 非战斗

    def test_is_connected(self):
        assert self.client.is_connected() is True

    def test_post_decision(self):
        path = os.path.join(FIXTURE_DIR, "combat_simple.json")
        self.client.load_fixture(path)
        ok = self.client.post_decision(Decision.play_card(0, 0))
        assert ok is True
        assert len(self.client.get_decision_log()) == 1

    def test_post_decision_logs_all(self):
        path = os.path.join(FIXTURE_DIR, "combat_simple.json")
        self.client.load_fixture(path)
        for i in range(3):
            self.client.post_decision(Decision.play_card(i, 0))
        assert len(self.client.get_decision_log()) == 3

    def test_sequence_mode(self):
        paths = [
            os.path.join(FIXTURE_DIR, "combat_simple.json"),
            os.path.join(FIXTURE_DIR, "card_reward.json"),
            os.path.join(FIXTURE_DIR, "rest_site.json"),
        ]
        ok = self.client.load_sequence(paths)
        assert ok is True

        # 初始状态是第一个 fixture
        assert self.client.get_state().in_combat is True

        # 发决策后自动切换到下一个 fixture
        self.client.post_decision(Decision.end_turn())
        assert self.client.get_state().in_combat is False  # card_reward is not combat
        assert self.client.get_status()["in_battle"] is False

        self.client.post_decision(Decision.pick_card(0))
        # 现在应该是第三个 fixture (rest_site)
        sd = self.client.get_raw_state()
        assert sd is not None
        assert sd.get("rest_site") is not None

    def test_get_raw_state(self):
        path = os.path.join(FIXTURE_DIR, "event.json")
        self.client.load_fixture(path)
        raw = self.client.get_raw_state()
        assert raw is not None
        assert raw["screen_type"] == "EVENT"
        assert "event" in raw

    def test_nonexistent_fixture(self):
        ok = self.client.load_fixture("nonexistent.json")
        assert ok is False
