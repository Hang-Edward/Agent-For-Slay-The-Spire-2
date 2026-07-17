from history.rewards import RewardCalculator


def state(player_hp, monster_hp, floor=1, gold=0):
    return {"player": {"current_hp": player_hp, "gold": gold},
            "monsters": [{"id": "m", "current_hp": monster_hp}], "floor": floor}


def test_transition_penalizes_hp_loss_and_rewards_enemy_damage():
    reward = RewardCalculator().transition(state(50, 30), state(45, 20))
    assert reward.components["player_hp_delta"] < 0
    assert reward.components["enemy_hp_delta"] > 0
    assert reward.total == round(sum(reward.components.values()), 4)


def test_terminal_outcome_dominates_shaping():
    calculator = RewardCalculator()
    win = calculator.terminal({"result": "victory", "floor": 50})
    loss = calculator.terminal({"result": "loss", "floor": 49})
    assert win.total > loss.total + 50
    assert win.reward_version == "1"
