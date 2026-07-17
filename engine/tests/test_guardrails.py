"""护栏层单元测试。"""

from communication.protocol import Decision
from state.game_state import GameState, Card, Monster
from strategy.guardrails import (
    GuardrailReport,
    GuardrailVerdict,
    InterventionLevel,
    StrategyGuardrail,
)


def _make_gs(**overrides) -> GameState:
    defaults = dict(
        screen_type="COMBAT", room_type="MONSTER", in_combat=True,
        decision_ready=True, action_in_flight=False, action_in_progress=False,
        state_revision=1,
        player_hp=40, player_max_hp=80, player_block=0,
        player_energy=3, player_energy_this_turn=3,
        gold=99, act=1, floor=3, ascension_level=2, char_class="IRONCLAD",
        player_powers=[], turn=1,
        potions=[], relics=[], options=[], teammates=[], team_actions=[],
        hand=[], deck=[], monsters=[], draw_pile_count=5,
        discard_pile=[], exhaust_pile=[], map_graph={}, raw={},
    )
    for key, value in overrides.items():
        if key == "player_gold":
            defaults["gold"] = value
        elif key == "player_phase":
            pass  # not a GameState field
        else:
            defaults[key] = value
    return GameState(**defaults)


def _card(block=0, damage=0, cost=1, is_playable=True,
          card_type="ATTACK", rarity="COMMON", has_target=True) -> Card:
    return Card(
        uuid="test", card_id="TEST", name="Test",
        cost=cost, cost_for_turn=cost,
        card_type=card_type, rarity=rarity,
        target_type="AnyEnemy" if has_target else "Self",
        has_target=has_target,
        is_playable=is_playable, playable_reason="OK",
        upgrades=0, damage=damage, block=block, magic_number=0,
        exhausts=False, ethereal=False,
    )


def _monster(hp=20, intent_damage=12, is_attacking=True, target_index=0) -> Monster:
    return Monster(
        monster_id="TEST_MONSTER", name="Test Monster",
        current_hp=hp, max_hp=hp, block=0,
        intent="ATTACK" if is_attacking else "BUFF",
        intent_damage=intent_damage, intent_hits=1,
        is_gone=False, half_dead=False, targetable=True,
        target_index=target_index,
    )


# ─── 战斗护栏测试 ─────────────────────────────────────


def test_lethal_threat_blocks_when_no_block():
    """面对致命伤害且无格挡/击杀时 BLOCK。"""
    gs = _make_gs(player_hp=15, player_block=0)
    gs.monsters = [_monster(hp=30, intent_damage=20)]
    # targetable_monsters 是派生属性, 由 monsters 自动更新
    gs.hand = [_card(block=0, damage=6)]
    state_data = {"game_state": gs}
    guard = StrategyGuardrail()
    report = guard.check("COMBAT", Decision.play_card(0, 0), state_data, [
        {"cards": [0], "names": ["Test"], "damage": 6, "block": 0,
         "damage_avoided_by_kills": 0, "estimated_hp_loss": 20, "score": 6},
    ])
    assert report.has_intervention()
    assert any(v.rule == "lethal_threat" for v in report.verdicts)


def test_minimum_defense_triggers_when_block_available():
    """手牌有格挡卡但选了全攻击序列 → 强制换格挡。"""
    gs = _make_gs(player_hp=40, player_block=0, player_energy=3)
    gs.monsters = [_monster(hp=30, intent_damage=18)]
    # targetable_monsters/alive_monsters 是由 monsters 自动计算的派生属性
    gs.hand = [_card(block=5, damage=0, card_type="SKILL", has_target=False),
               _card(block=0, damage=6)]
    state_data = {"game_state": gs}
    guard = StrategyGuardrail()
    report = guard.check("COMBAT", Decision.play_card(1, 0), state_data, [
        {"cards": [1], "names": ["Strike"], "damage": 6, "block": 0,
         "damage_avoided_by_kills": 0, "estimated_hp_loss": 18, "score": 6},
        {"cards": [0], "names": ["Defend"], "damage": 0, "block": 5,
         "damage_avoided_by_kills": 0, "estimated_hp_loss": 13, "score": 5},
    ])
    interventions = report.interventions()
    # 应有 minimum_defense 干预
    assert any(v.rule == "minimum_defense" for v in interventions)


def test_emergency_potion_on_lethal():
    """面对致命伤害且药水可用 ⇒ 强制用药。"""
    gs = _make_gs(player_hp=10, player_block=0)
    gs.monsters = [_monster(hp=30, intent_damage=15)]
    # targetable_monsters/alive_monsters 是由 monsters 自动计算的派生属性
    gs.hand = [_card(block=0, damage=6)]
    gs.potions = [{"slot": 0, "id": "POTION_BLOCK", "name": "Block Potion",
                   "can_use": True, "target_type": "Self"}]
    state_data = {"game_state": gs}
    guard = StrategyGuardrail()
    report = guard.check("COMBAT", Decision.play_card(0, 0), state_data, [
        {"cards": [0], "damage": 6, "block": 0, "score": 6},
    ])
    overrides = [v for v in report.verdicts if v.rule == "emergency_potion"]
    assert len(overrides) == 1
    assert overrides[0].corrected_decision is not None
    assert overrides[0].corrected_decision.type == "use_potion"


def test_no_playable_cards_triggers_end_turn():
    """没有合法可出牌时强制结束回合。"""
    gs = _make_gs(player_hp=40, player_energy=1)
    gs.hand = [_card(cost=3, is_playable=True)]
    gs.monsters = [_monster()]
    # targetable_monsters/alive_monsters 是由 monsters 自动计算的派生属性
    state_data = {"game_state": gs}
    guard = StrategyGuardrail()
    report = guard.check("COMBAT", Decision.play_card(0, 0), state_data, [
        {"cards": [0], "damage": 6, "block": 0, "score": 6},
    ])
    interventions = report.interventions()
    assert any(v.rule == "no_playable_cards" for v in interventions)


# ─── 卡牌奖励护栏测试 ────────────────────────────────


def test_never_skip_good_card():
    """不跳过含高价值牌的奖励。"""
    guard = StrategyGuardrail()
    state_data = {"deck": [{"name": "Strike"}, {"name": "Defend"}]}
    report = guard.check("CARD_REWARD", Decision.skip_reward(), state_data, [
        {"index": 0, "name": "Strike", "rarity": "BASIC", "damage": 6, "block": 0, "type": "ATTACK"},
        {"index": 1, "name": "Demon Form", "rarity": "RARE", "damage": 0, "block": 0, "type": "POWER"},
        {"index": 2, "name": "Shrug It Off", "rarity": "COMMON", "damage": 0, "block": 8, "type": "SKILL"},
    ])
    overrides = [v for v in report.verdicts if v.rule == "never_skip_good_card"]
    assert len(overrides) == 1
    assert overrides[0].corrected_decision.type == "pick_card"


def test_avoid_curse_in_reward():
    """不选诅咒卡牌。"""
    guard = StrategyGuardrail()
    state_data = {"deck": [{"name": "Strike"}]}
    report = guard.check("CARD_REWARD", Decision.pick_card(0), state_data, [
        {"index": 0, "name": "Writhe", "rarity": "CURSE", "damage": 0, "block": 0, "type": "CURSE"},
    ])
    assert any(v.rule == "avoid_curse" for v in report.verdicts)


def test_skip_skip_when_all_common_bad():
    """三张都是低价值白卡时可以跳过。"""
    guard = StrategyGuardrail()
    state_data = {"deck": [{"name": "Strike"}, {"name": "Defend"}]}
    report = guard.check("CARD_REWARD", Decision.skip_reward(), state_data, [
        {"index": 0, "name": "Strike", "rarity": "BASIC", "damage": 6, "block": 0, "type": "ATTACK"},
        {"index": 1, "name": "Defend", "rarity": "BASIC", "damage": 0, "block": 5, "type": "SKILL"},
        {"index": 2, "name": "Anger", "rarity": "COMMON", "damage": 6, "block": 0, "type": "ATTACK"},
    ])
    assert not report.has_intervention()


# ─── 商店/宝箱护栏测试 ──────────────────────────────


def test_always_open_chest():
    """宝箱界面不跳过。"""
    guard = StrategyGuardrail()
    report = guard.check("TREASURE", Decision.end_turn(), {}, [
        {"kind": "open_chest", "id": "Chest", "name": "Chest", "enabled": True},
    ])
    assert any(v.rule == "always_open_chest" for v in report.verdicts)


# ─── 地图护栏测试 ──────────────────────────────


def test_avoid_elite_when_low_hp():
    """HP<40%时避开精英路线。"""
    guard = StrategyGuardrail()
    state_data = {"player": {"current_hp": 20, "max_hp": 80}, "potions": []}
    report = guard.check("MAP", Decision.choose_option(0), state_data, [
        {"option_index": 0, "kind": "elite", "id": "elite_node", "name": "Elite", "score": 20.0, "enabled": True},
        {"option_index": 1, "kind": "monster", "id": "monster_node", "name": "Monster", "score": 10.0, "enabled": True},
    ])
    overrides = [v for v in report.verdicts if v.rule == "avoid_elite_low_hp"]
    assert len(overrides) == 1
    assert overrides[0].corrected_decision.option_index == 1


# ─── 篝火护栏测试 ──────────────────────────────


def test_rest_when_critical_hp():
    """HP<30%时强制休息。"""
    guard = StrategyGuardrail()
    state_data = {"player": {"current_hp": 15, "max_hp": 80}}
    report = guard.check("REST", Decision.smith(0), state_data, [
        {"kind": "rest", "enabled": True},
        {"kind": "smith", "enabled": True},
    ])
    overrides = [v for v in report.verdicts if v.rule == "rest_when_critical"]
    assert len(overrides) == 1
    assert overrides[0].corrected_decision.type == "rest"


def test_smith_allowed_when_hp_above_threshold():
    """HP>50%时可以正常锻造。"""
    guard = StrategyGuardrail()
    state_data = {"player": {"current_hp": 60, "max_hp": 80}}
    report = guard.check("REST", Decision.smith(0), state_data, [])
    assert not report.has_intervention()


# ─── 通用护栏测试 ──────────────────────────────


def test_disabled_option_overridden():
    """不选已禁用的选项。"""
    guard = StrategyGuardrail()
    report = guard.check("CHOICE", Decision.choose_option(0), {}, [
        {"index": 0, "option_index": 0, "enabled": False, "name": "Disabled"},
        {"index": 1, "option_index": 1, "enabled": True, "name": "Enabled"},
    ])
    overrides = [v for v in report.verdicts if v.rule == "disabled_option"]
    assert len(overrides) == 1
    assert overrides[0].corrected_decision.option_index == 1


# ─── LocalPolicy 集成测试 ──────────────────────────


def test_policy_produces_guardrail_report_on_intervention():
    """LocalPolicy 决策中有护栏干预时返回报告。"""
    from types import SimpleNamespace
    from policy.local_policy import LocalPolicy

    policy = LocalPolicy()
    handler = SimpleNamespace(screen_type="COMBAT", fallback_decision=lambda _: Decision.end_turn())
    gs = _make_gs(player_hp=10, player_block=0, player_energy=3)
    gs.monsters = [_monster(hp=30, intent_damage=20)]
    # targetable_monsters/alive_monsters 是由 monsters 自动计算的派生属性
    gs.hand = [_card(block=0, damage=6)]
    state_data = {"game_state": gs, "playable_cards": [(0, gs.hand[0])], "has_alive_monsters": True}

    result = policy.decide(handler, state_data, [
        {"cards": [0], "names": ["Strike"], "damage": 6, "block": 0,
         "damage_avoided_by_kills": 0, "estimated_hp_loss": 20, "score": 6},
    ])
    assert result.guardrail is not None
    assert result.guardrail.has_intervention()


def test_policy_no_guardrail_on_safe_decision():
    """安全决策不触发护栏。"""
    from types import SimpleNamespace
    from policy.local_policy import LocalPolicy

    policy = LocalPolicy()
    handler = SimpleNamespace(screen_type="CHOICE", fallback_decision=lambda _: Decision.end_turn())
    state_data = {"screen_type": "MAIN_MENU"}
    result = policy.decide(handler, state_data, [
        {"option_index": 0, "kind": "singleplayer", "name": "Single Player",
         "enabled": True, "score": 0},
    ])
    assert result.guardrail is None
    assert result.decision.type == "choose_option"
