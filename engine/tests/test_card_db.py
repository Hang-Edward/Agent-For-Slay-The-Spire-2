"""测试卡牌数据库。"""

import os

from data.card_db import CardDatabase


class TestCardDatabase:
    def setup_method(self):
        engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(engine_dir, "data")
        self.db = CardDatabase(data_dir)

    def test_loads_ironclad_cards(self):
        assert len(self.db._cards) > 10

    def test_get_strike(self):
        info = self.db.get_card_info("Strike_R")
        assert info is not None
        assert info["name"] == "Strike"
        assert info["cost"] == 1
        assert info["type"] == "ATTACK"

    def test_get_description(self):
        desc = self.db.get_description("Bash")
        assert len(desc) > 0

    def test_get_upgrade_description(self):
        desc = self.db.get_description("Bash", upgraded=True)
        assert len(desc) > 0

    def test_get_tags(self):
        tags = self.db.get_tags("Cleave")
        assert "aoe" in tags
        assert "attack" in tags

    def test_get_synergy(self):
        synergy = self.db.get_synergy("Heavy Blade")
        assert "strength" in synergy

    def test_format_card_for_prompt_known(self):
        formatted = self.db.format_card_for_prompt("Strike_R")
        assert "Strike" in formatted
        assert "Cost: 1" in formatted

    def test_format_card_for_prompt_unknown(self):
        formatted = self.db.format_card_for_prompt("UnknownCardXYZ")
        assert formatted == ""

    def test_singleton(self):
        db1 = CardDatabase.get_default()
        db2 = CardDatabase.get_default()
        assert db1 is db2
