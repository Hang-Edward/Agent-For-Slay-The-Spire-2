"""测试 DryRunClient — 模拟 LLM 响应。"""

from llm.dryrun_client import DryRunClient


class TestDryRunClient:
    def setup_method(self):
        self.client = DryRunClient()

    def test_is_configured(self):
        assert self.client.is_configured() is True

    def test_name(self):
        assert self.client.name == "DryRun"

    def test_think_combat(self):
        resp, elapsed = self.client.think("PLAY 0 0 against monster")
        assert resp == "PLAY 0 0"
        assert elapsed > 0

    def test_think_card_reward(self):
        resp, elapsed = self.client.think("Reward Cards: Strike, Defend, Bash")
        assert resp == "PICK 0"

    def test_think_rest(self):
        resp, elapsed = self.client.think("REST or SMITH")
        assert resp == "REST"

    def test_think_event(self):
        resp, elapsed = self.client.think("=== Big Fish ===")
        assert resp == "CHOOSE 0"

    def test_think_event_with_reward_keywords(self):
        """事件文本可能包含 PICK/REST，但 === 标志优先匹配事件。"""
        resp, elapsed = self.client.think("=== Mysterious Woman === You can choose to REST or PICK a reward")
        assert resp == "CHOOSE 0", "=== should trigger event detection"

    def test_call_count(self):
        self.client.think("test")
        self.client.think("test")
        assert self.client.call_count == 2

    def test_reset(self):
        self.client.think("test")
        self.client.reset()
        assert self.client.call_count == 0
        assert self.client.last_prompt == ""

    def test_last_prompt(self):
        self.client.think("hello world")
        assert "hello world" in self.client.last_prompt
