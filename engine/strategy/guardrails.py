"""策略护栏 — 在模型决策前后强制检查领域规则。

每条护栏独立开关，记录干预日志供后续训练用。
护栏只在"明显错误"时介入修正，不取代模型决策。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from communication.protocol import Decision, SCREEN_COMBAT, SCREEN_CARD_REWARD, SCREEN_REWARDS, SCREEN_SHOP, SCREEN_TREASURE, SCREEN_MAP, SCREEN_EVENT, SCREEN_REST, SCREEN_GAME_OVER, SCREEN_VICTORY

logger = logging.getLogger("guardrails")


class InterventionLevel(Enum):
    """护栏干预等级——越往下越强。"""
    PASS = "pass"               # 通过，无干预
    WARN = "warn"               # 记录警告但不修改
    OVERRIDE = "override"       # 修改决策参数
    BLOCK = "block"             # 阻止此决策，换用安全后备


@dataclass
class GuardrailVerdict:
    """单条护栏的判定结果。"""
    rule: str
    level: InterventionLevel
    message: str = ""
    corrected_decision: Decision | None = None

    def is_pass(self) -> bool:
        return self.level == InterventionLevel.PASS


@dataclass
class GuardrailReport:
    """一次决策的全部护栏检查汇总。"""
    screen_type: str
    verdicts: list[GuardrailVerdict] = field(default_factory=list)
    overridden: bool = False
    final_decision: Decision | None = None

    def has_intervention(self) -> bool:
        return any(v.level in {InterventionLevel.OVERRIDE, InterventionLevel.BLOCK} for v in self.verdicts)

    def interventions(self) -> list[GuardrailVerdict]:
        return [v for v in self.verdicts if v.level in {InterventionLevel.OVERRIDE, InterventionLevel.BLOCK}]

    @property
    def summary(self) -> str:
        if not self.has_intervention():
            return "all pass"
        parts = [f"{v.rule}={v.level.value}" for v in self.verdicts if v.level != InterventionLevel.PASS]
        return "; ".join(parts)


class StrategyGuardrail:
    """领域知识护栏集合。每条规则聚焦一个已验证的常见错误模式。"""

    def __init__(self, enabled: bool = True, log_interventions: bool = True):
        self.enabled = enabled
        self.log_interventions = log_interventions

    def check(self, screen_type: str, decision: Decision,
              state_data: dict, candidates: list[dict] | None = None) -> GuardrailReport:
        """对即将执行的决策执行全部适用护栏检查。"""
        report = GuardrailReport(screen_type=screen_type)
        if not self.enabled:
            report.overridden = False
            report.final_decision = decision
            return report

        checkers = {
            SCREEN_COMBAT: self._check_combat,
            SCREEN_CARD_REWARD: self._check_card_reward,
            SCREEN_REWARDS: self._check_rewards,
            SCREEN_SHOP: self._check_shop,
            SCREEN_TREASURE: self._check_treasure,
            SCREEN_MAP: self._check_map,
            SCREEN_REST: self._check_rest,
            SCREEN_EVENT: self._check_event,
        }
        checker = checkers.get(screen_type, self._check_generic)
        verdicts = checker(decision, state_data, candidates or [])
        report.verdicts = verdicts

        overrides = [v for v in verdicts if v.level == InterventionLevel.OVERRIDE]
        blocks = [v for v in verdicts if v.level == InterventionLevel.BLOCK]

        if overrides:
            report.overridden = True
            report.final_decision = overrides[-1].corrected_decision
            if self.log_interventions:
                for v in overrides:
                    logger.warning("GUARDRAIL OVERRIDE [%s]: %s", v.rule, v.message)
        elif blocks:
            report.overridden = True
            report.final_decision = self._safe_fallback(screen_type, decision, state_data)
            if self.log_interventions:
                for v in blocks:
                    logger.warning("GUARDRAIL BLOCK [%s]: %s", v.rule, v.message)
        else:
            report.final_decision = decision

        return report

    # ─── 内部检查方法 ──────────────────────────────────────

    def _check_combat(self, decision: Decision, state: dict,
                      candidates: list[dict]) -> list[GuardrailVerdict]:
        verdicts: list[GuardrailVerdict] = []
        gs = state.get("game_state")
        if not gs:
            return verdicts

        incoming = sum(
            m.intent_damage * max(1, m.intent_hits)
            for m in getattr(gs, "alive_monsters", [])
            if hasattr(m, "is_attacking") and m.is_attacking
        )
        block = getattr(gs, "player_block", 0)
        hp = getattr(gs, "player_hp", 1)
        energy = getattr(gs, "player_energy", 0)
        hand = list(getattr(gs, "hand", []))

        # R1: 面对致命伤害时必须阻挡或击杀攻击者
        unblocked = max(0, incoming - block)
        if decision.type in {"play_card", "end_turn"}:
            sel_candidate = self._find_selected_candidate(decision, candidates)
            cards_in_seq = sel_candidate.get("cards", []) if sel_candidate else []
            seq_block = sum(
                hand[i].block if i < len(hand) else 0
                for i in cards_in_seq
            ) if hand else 0
            seq_kill_damage = sel_candidate.get("damage", 0) if sel_candidate else 0

            # 检查：是否可击杀正在攻击的敌人
            kills_attacker = False
            if sel_candidate and hand:
                remaining = seq_kill_damage
                for m in sorted(
                    (m for m in getattr(gs, "alive_monsters", []) if m.is_attacking),
                    key=lambda m: m.current_hp + m.block,
                ):
                    if remaining >= m.current_hp + m.block:
                        remaining -= m.current_hp + m.block
                        kills_attacker = True
                    else:
                        break

            total_prevent = seq_block + (sel_candidate.get("damage_avoided_by_kills", 0) if sel_candidate else 0)

            if unblocked >= hp and decision.type != "use_potion":
                verdicts.append(GuardrailVerdict(
                    rule="lethal_threat",
                    level=InterventionLevel.BLOCK,
                    message=f"LETHAL: incoming={incoming}, block={block}, hp={hp}, 序列未提供足够格挡或击杀",
                ))
            elif unblocked >= int(hp * 0.4) and total_prevent < unblocked * 0.5:
                hand_has_block = any(c.block > 0 and c.is_playable and c.cost_for_turn <= energy for c in hand)
                if hand_has_block and seq_block == 0 and not kills_attacker:
                    verdicts.append(GuardrailVerdict(
                        rule="minimum_defense",
                        level=InterventionLevel.OVERRIDE,
                        message=f"HIGH incoming={incoming} 但序列0格挡, 手牌有挡牌可用",
                        corrected_decision=self._force_block(candidates, gs),
                    ))

        # R2: 药水使用——面对致命伤害时强制用药
        if unblocked >= hp and decision.type == "play_card":
            pots = list(getattr(gs, "potions", []))
            useful_pot = next(
                (p for p in pots if p.get("can_use", False) and p.get("slot", -1) >= 0),
                None,
            )
            if useful_pot and not decision.type == "use_potion":
                verdicts.append(GuardrailVerdict(
                    rule="emergency_potion",
                    level=InterventionLevel.OVERRIDE,
                    message=f"致命伤害时强制用药 slot={useful_pot.get('slot')}",
                    corrected_decision=Decision.use_potion(
                        int(useful_pot["slot"]),
                        self._best_target_index(gs),
                    ),
                ))

        # R3: 无可用牌时结束回合（已有 fallback，额外安全网）
        has_playable = any(
            c.is_playable and c.cost_for_turn <= energy
            for c in hand
        )
        if not has_playable and decision.type != "end_turn":
            verdicts.append(GuardrailVerdict(
                rule="no_playable_cards",
                level=InterventionLevel.OVERRIDE,
                message="手牌无可用牌, 强制结束回合",
                corrected_decision=Decision.end_turn(),
            ))

        return verdicts

    def _check_card_reward(self, decision: Decision, state: dict,
                           candidates: list[dict]) -> list[GuardrailVerdict]:
        verdicts: list[GuardrailVerdict] = []

        # R4: 不要跳过含好牌的奖励
        if decision.type == "pick_card" and decision.card_index == -1:
            if candidates:
                high_value = [
                    c for c in candidates
                    if self._card_priority(c) >= 4.0
                ]
                if high_value:
                    best = max(high_value, key=self._card_priority)
                    verdicts.append(GuardrailVerdict(
                        rule="never_skip_good_card",
                        level=InterventionLevel.OVERRIDE,
                        message=f"跳过含高价值牌: {best.get('name', '?')}",
                        corrected_decision=Decision.pick_card(int(best["index"])),
                    ))

        # R5: 不选诅咒
        if decision.type == "pick_card" and decision.card_index >= 0:
            for c in candidates:
                if int(c.get("index", -1)) == decision.card_index:
                    card_type = str(c.get("type", c.get("card_type", ""))).upper()
                    if card_type in {"CURSE", "STATUS"}:
                        verdicts.append(GuardrailVerdict(
                            rule="avoid_curse",
                            level=InterventionLevel.BLOCK,
                            message=f"试图选择诅咒/状态: {c.get('name', '?')}",
                        ))
                    break

        # R6: 牌组超过30张时不再加廉价白卡
        deck = state.get("deck", [])
        if len(deck) >= 30:
            if decision.type == "pick_card" and decision.card_index >= 0:
                for c in candidates:
                    if int(c.get("index", -1)) == decision.card_index:
                        if str(c.get("rarity", "")).upper() == "COMMON" and self._card_priority(c) < 2.0:
                            # 看看其他选项有没有更好
                            better = [x for x in candidates if self._card_priority(x) >= 3.0 and int(x.get("index", -1)) != decision.card_index]
                            if better:
                                best = max(better, key=self._card_priority)
                                verdicts.append(GuardrailVerdict(
                                    rule="large_deck_bloat",
                                    level=InterventionLevel.OVERRIDE,
                                    message=f"牌组{len(deck)}张, 不拿低价值白卡 {c.get('name','?')}",
                                    corrected_decision=Decision.pick_card(int(best["index"])),
                                ))
                        break

        return verdicts

    def _check_rewards(self, decision: Decision, state: dict,
                       candidates: list[dict]) -> list[GuardrailVerdict]:
        verdicts: list[GuardrailVerdict] = []

        # R7: 奖励界面"继续"前确认已拿全部奖励
        if decision.type == "choose_option":
            option_name = ""
            for c in candidates:
                if int(c.get("option_index", -1)) == decision.option_index:
                    option_name = str(c.get("kind", c.get("name", ""))).lower()
                    break
            if option_name in {"proceed", "continue"}:
                remaining_rewards = [
                    c for c in candidates
                    if c.get("kind") in {"relic", "card", "card_reward", "gold", "potion"}
                    and c.get("enabled", True) and not c.get("selected", False)
                ]
                if remaining_rewards:
                    verdicts.append(GuardrailVerdict(
                        rule="take_all_rewards_first",
                        level=InterventionLevel.BLOCK,
                        message=f"有 {len(remaining_rewards)} 个可用奖励未领取",
                    ))

        return verdicts

    def _check_shop(self, decision: Decision, state: dict,
                    candidates: list[dict]) -> list[GuardrailVerdict]:
        verdicts: list[GuardrailVerdict] = []

        # R6b: 不买诅咒
        if decision.type == "choose_option":
            for c in candidates:
                if int(c.get("option_index", -1)) == decision.option_index:
                    rid = str(c.get("id", "")).lower()
                    desc = str(c.get("description", "")).lower()
                    if "curse" in rid or "诅咒" in desc:
                        verdicts.append(GuardrailVerdict(
                            rule="shop_avoid_curse",
                            level=InterventionLevel.BLOCK,
                            message=f"商店中尝试购买诅咒: {c.get('name','?')}",
                        ))
                    break

        # R8: 有钱时优先买关键遗物/药水
        player = state.get("player", {})
        gold = int(player.get("gold", 0))
        if gold >= 100 and decision.type == "choose_option":
            for c in candidates:
                kind = str(c.get("kind", "")).lower()
                if kind == "proceed" and decision.option_index == int(c.get("option_index", -1)):
                    relic_offers = [
                        x for x in candidates
                        if x.get("kind") in {"relic", "relic_offer"}
                        and x.get("enabled", True)
                    ]
                    if relic_offers and gold >= int(relic_offers[0].get("cost", 999)):
                        verdicts.append(GuardrailVerdict(
                            rule="buy_useful_relic_first",
                            level=InterventionLevel.BLOCK,
                            message=f"商店直接离开但金={gold}足够购买遗物",
                        ))

        return verdicts

    def _check_treasure(self, decision: Decision, state: dict,
                        candidates: list[dict]) -> list[GuardrailVerdict]:
        # R9: 宝箱永远打开拿奖励
        verdicts: list[GuardrailVerdict] = []
        if decision.type in {"end_turn", "proceed"}:
            has_chest = any(
                c.get("kind") in {"open_chest", "chest"} and c.get("enabled", True)
                for c in candidates
            )
            if has_chest:
                verdicts.append(GuardrailVerdict(
                    rule="always_open_chest",
                    level=InterventionLevel.BLOCK,
                    message="宝箱界面试图跳过",
                ))
        # 如果有 relic/chest 可选且未选，提醒但不强制
        return verdicts

    def _check_map(self, decision: Decision, state: dict,
                   candidates: list[dict]) -> list[GuardrailVerdict]:
        verdicts: list[GuardrailVerdict] = []
        player = state.get("player", {})
        hp = int(player.get("current_hp", 80))
        max_hp = int(player.get("max_hp", 80))
        hp_ratio = hp / max(max_hp, 1)

        # R10: HP 低时不走精英路线
        if decision.type == "choose_option":
            for c in candidates:
                if int(c.get("option_index", -1)) == decision.option_index:
                    kind = str(c.get("kind", "")).lower()
                    if kind == "elite" and hp_ratio < 0.40:
                        non_elite = [
                            x for x in candidates
                            if str(x.get("kind", "")).lower() != "elite"
                            and x.get("enabled", True)
                            and int(x.get("option_index", -1)) != decision.option_index
                        ]
                        if non_elite:
                            best_safe = max(non_elite, key=lambda x: float(x.get("score", 0)))
                            verdicts.append(GuardrailVerdict(
                                rule="avoid_elite_low_hp",
                                level=InterventionLevel.OVERRIDE,
                                message=f"HP={hp}/{max_hp}({hp_ratio:.0%}) < 40%, 避免精英路线",
                                corrected_decision=Decision.choose_option(int(best_safe["option_index"])),
                            ))
                    elif kind == "elite" and hp_ratio < 0.60:
                        # 有药水时可以冒险
                        pots = state.get("potions", [])
                        has_healing_pot = any("heal" in str(p.get("id", "")).lower() for p in pots)
                        if not has_healing_pot:
                            non_elite = [
                                x for x in candidates
                                if str(x.get("kind", "")).lower() != "elite"
                                and x.get("enabled", True)
                            ]
                            if non_elite:
                                verdicts.append(GuardrailVerdict(
                                    rule="elite_risk_warning",
                                    level=InterventionLevel.WARN,
                                    message=f"HP={hp}/{max_hp}({hp_ratio:.0%})<60% 且无治疗药水, 精英路线风险较高",
                                ))
                    break

        return verdicts

    def _check_rest(self, decision: Decision, state: dict,
                    candidates: list[dict]) -> list[GuardrailVerdict]:
        verdicts: list[GuardrailVerdict] = []
        player = state.get("player", {})
        hp = int(player.get("current_hp", 80))
        max_hp = int(player.get("max_hp", 80))
        hp_ratio = hp / max(max_hp, 1)

        # R11: HP 极低时优先休息，不锻造
        if decision.type == "smith":
            if hp_ratio < 0.30:
                has_rest_option = any(
                    c.get("kind") == "rest" and c.get("enabled", True)
                    for c in candidates
                )
                if has_rest_option:
                    verdicts.append(GuardrailVerdict(
                        rule="rest_when_critical",
                        level=InterventionLevel.OVERRIDE,
                        message=f"HP={hp}/{max_hp}({hp_ratio:.0%}) < 30%, 强制休息",
                        corrected_decision=Decision.rest(),
                    ))

        # R12: HP 低于 50% 且后面有精英/Boss 时考虑休息
        if decision.type == "smith" and hp_ratio < 0.50:
            upcoming_map = state.get("map", {})
            nodes = upcoming_map.get("nodes", [])
            current_id = upcoming_map.get("current_node_id", "")
            upcoming_elite_or_boss = any(
                n.get("type") in {"ELITE", "BOSS"}
                for n in nodes
            )
            if upcoming_elite_or_boss:
                has_rest_option = any(
                    c.get("kind") == "rest" and c.get("enabled", True)
                    for c in candidates
                )
                if has_rest_option:
                    verdicts.append(GuardrailVerdict(
                        rule="rest_before_danger",
                        level=InterventionLevel.WARN,
                        message=f"HP={hp}/{max_hp}({hp_ratio:.0%}) < 50% 且前方有精英/Boss",
                    ))

        return verdicts

    def _check_event(self, decision: Decision, state: dict,
                     candidates: list[dict]) -> list[GuardrailVerdict]:
        verdicts: list[GuardrailVerdict] = []

        # R13: 事件中不选立即致命或明显有害的选项
        if decision.type == "choose_option":
            for c in candidates:
                if int(c.get("option_index", -1)) == decision.option_index:
                    desc = str(c.get("description", "")).lower()
                    name = str(c.get("name", "")).lower()
                    text = f"{name} {desc}"
                    player = state.get("player", {})
                    hp = int(player.get("current_hp", 80))
                    max_hp = int(player.get("max_hp", 80))

                    loss_hp = 0
                    for token in ("lose ", "take ", "伤害", "失去", "损失"):
                        if token in text:
                            try:
                                idx = text.index(token) + len(token)
                                num_str = ""
                                for ch in text[idx:]:
                                    if ch.isdigit() or ch == "-":
                                        num_str += ch
                                    else:
                                        break
                                if num_str:
                                    loss_hp = int(num_str)
                            except (ValueError, IndexError):
                                pass

                    if loss_hp >= hp:
                        # 有其他安全选项吗？
                        safe = [
                            x for x in candidates
                            if int(x.get("option_index", -1)) != decision.option_index
                            and x.get("enabled", True)
                        ]
                        if safe:
                            verdicts.append(GuardrailVerdict(
                                rule="avoid_lethal_event",
                                level=InterventionLevel.BLOCK,
                                message=f"事件选项 {decision.option_index} 立刻致死 (HP={hp}, 损失={loss_hp})",
                            ))
                    break

        return verdicts

    def _check_generic(self, decision: Decision, state: dict,
                       candidates: list[dict]) -> list[GuardrailVerdict]:
        """所有屏幕通用的基础检查。"""
        verdicts: list[GuardrailVerdict] = []

        # R14: 不选 disabled 选项
        if decision.type == "choose_option":
            for c in candidates:
                if int(c.get("option_index", -1)) == decision.option_index:
                    if not c.get("enabled", True):
                        enabled = [
                            x for x in candidates
                            if x.get("enabled", True)
                        ]
                        if enabled:
                            alt = min(enabled, key=lambda x: abs(int(x.get("index", 0)) - decision.option_index))
                            verdicts.append(GuardrailVerdict(
                                rule="disabled_option",
                                level=InterventionLevel.OVERRIDE,
                                message=f"选项 {decision.option_index} 已禁用, 改选 {alt.get('index', '?')}",
                                corrected_decision=Decision.choose_option(int(alt["index"])),
                            ))
                    break

        return verdicts

    # ─── 辅助方法 ──────────────────────────────────────────

    def _find_selected_candidate(self, decision: Decision, candidates: list[dict]) -> dict | None:
        if decision.type in {"play_card", "end_turn"}:
            if not candidates:
                return None
            for c in candidates:
                if c.get("action_key", "").startswith("cards:"):
                    cards_str = c["action_key"].replace("cards:", "")
                    first_card = cards_str.split(",")[0] if cards_str else ""
                    if first_card and int(decision.hand_index) == int(first_card.split(",")[0]):
                        return c
            return candidates[0] if candidates else None
        if decision.type == "choose_option":
            for c in candidates:
                if int(c.get("option_index", -1)) == decision.option_index:
                    return c
        return None

    def _force_block(self, candidates: list[dict], gs) -> Decision | None:
        """在所有候选序列中找到格挡最多的。"""
        block_seq = None
        max_block = -1
        for c in candidates:
            seq_block = c.get("block", 0)
            if seq_block > max_block:
                max_block = seq_block
                block_seq = c
        if block_seq:
            cards = block_seq.get("cards", [])
            if cards:
                monster_idx = self._best_target_index(gs)
                return Decision.play_card(int(cards[0]), monster_idx)
        return None

    def _best_target_index(self, gs) -> int:
        targets = list(getattr(gs, "targetable_monsters", []))
        if not targets:
            return 0
        target = min(targets, key=lambda m: m.current_hp + m.block)
        return target.target_index if target.target_index >= 0 else targets.index(target)

    def _card_priority(self, candidate: dict) -> float:
        """基于稀有度和角色需求给候选卡牌打分。"""
        rarity = str(candidate.get("rarity", "")).upper()
        base = {"RARE": 5.0, "UNCOMMON": 3.0, "COMMON": 1.0, "CURSE": -10.0, "STATUS": -10.0}.get(rarity, 0.0)
        attack = float(candidate.get("damage", 0))
        block = float(candidate.get("block", 0))
        if attack > 0:
            base += min(2.0, attack / 10)
        if block > 0:
            base += min(1.5, block / 10)
        return base

    def _safe_fallback(self, screen_type: str, orig: Decision, state: dict) -> Decision:
        """护栏 BLOCK 时的通用安全后备。"""
        if screen_type == SCREEN_COMBAT:
            return Decision.end_turn()
        if screen_type in {SCREEN_CARD_REWARD, SCREEN_REWARDS}:
            return Decision.skip_reward()
        if screen_type == SCREEN_REST:
            return Decision.rest()
        return Decision.end_turn()
