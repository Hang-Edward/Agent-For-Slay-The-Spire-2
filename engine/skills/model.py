"""Skill definitions for the AI strategy system.

Each Skill is a specific, toggleable behavior rule that guides the LLM's decisions.
Unlike vague sliders, skills are concrete instructions written into the prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Skill:
    """A single strategy skill — a concrete instruction for the LLM.

    Skills are:
    - Toggleable (on/off)
    - Have clear trigger conditions
    - Produce specific behavioral changes
    - Can conflict with each other (first-match priority)
    """

    id: str
    name: str
    description: str
    prompt_instruction: str  # What gets inserted into the LLM prompt
    enabled: bool = False
    category: str = "general"  # combat, deckbuilding, pathing, resource
    priority: int = 0  # Higher = overrides lower

    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", data.get("id", "")),
            description=data.get("description", ""),
            prompt_instruction=data.get("prompt_instruction", ""),
            enabled=data.get("enabled", False),
            category=data.get("category", "general"),
            priority=data.get("priority", 0),
        )


class SkillsRegistry:
    """Manages all available skills and their states."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._load_defaults()

    def _load_defaults(self):
        """Load built-in default skills."""
        defaults = [
            Skill(
                id="focus_fire",
                name="集火残血",
                description="优先攻击血量最低的怪物",
                prompt_instruction="Priority target: the monster with the lowest current HP. Focus fire to eliminate threats one by one.",
                category="combat",
            ),
            Skill(
                id="block_when_attacked",
                name="防御优先",
                description="当怪物即将攻击时，优先打出格挡牌",
                prompt_instruction="If any monster's intent is ATTACK and your block is less than their damage, prioritize playing block cards before attacks.",
                category="combat",
            ),
            Skill(
                id="save_potions",
                name="省用药水",
                description="只在紧急情况下使用药水（HP低于30%或面对Boss）",
                prompt_instruction="Only use potions in emergencies: when your HP is below 30% of max, or when facing a boss encounter.",
                category="resource",
                priority=5,
            ),
            Skill(
                id="no_overkill",
                name="避免过量",
                description="不对即将死亡的怪物过量输出，将伤害分配给其他目标",
                prompt_instruction="Avoid overkill: if a monster will die from minimal damage, allocate remaining attacks to other targets.",
                category="combat",
            ),
            Skill(
                id="setup_first",
                name="蓄爆优先",
                description="优先上Buff和Debuff，再考虑输出",
                prompt_instruction="Prioritize playing setup cards (powers, buffs, debuffs) before dealing damage. Apply vulnerable and strength first.",
                category="combat",
            ),
            Skill(
                id="aoe_priority",
                name="群攻优先",
                description="面对多个敌人时优先使用群体攻击",
                prompt_instruction="Against 2+ enemies, prioritize AoE/multi-target cards to damage all enemies simultaneously.",
                category="combat",
            ),
            Skill(
                id="conserve_energy",
                name="保留能量",
                description="保留至少1点能量给下回合的关键牌",
                prompt_instruction="Consider saving 1 energy for next turn if you have expensive key cards coming. Don't waste energy on marginal plays.",
                category="resource",
            ),
            Skill(
                id="aggressive",
                name="激进输出",
                description="优先最大化伤害输出，可以接受少量伤害",
                prompt_instruction="Prioritize dealing maximum damage each turn. It's acceptable to take some damage to deal more damage. End the turn only when you have no useful plays.",
                category="combat",
            ),
            Skill(
                id="elite_path",
                name="精英路线",
                description="路线选择上优先走精英怪路线（非战斗时生效）",
                prompt_instruction="When choosing map paths, prioritize routes with more elite encounters for better rewards.",
                category="pathing",
            ),
            Skill(
                id="adaptive_hp_trade",
                name="动态卖血",
                description="根据致死风险、血量比例和击杀收益决定卖血或保血",
                prompt_instruction=(
                    "Use the whole-turn risk budget. Do not block automatically: accept small HP loss when it secures "
                    "a kill or major tempo and HP is healthy, but preserve HP before elites/bosses and never accept lethal risk."
                ),
                category="combat",
                priority=8,
            ),
            Skill(
                id="deck_coherence",
                name="卡组完整性",
                description="根据卡组职责缺口和重复饱和度选牌",
                prompt_instruction=(
                    "For card rewards, use the deck profile and marginal deck-fit score. Fill missing damage, block, draw, "
                    "energy, or scaling; skip mediocre cards that only bloat the deck."
                ),
                category="deckbuilding",
                priority=7,
            ),
            Skill(
                id="adaptive_pathing",
                name="动态路线",
                description="在奖励密度、战损、金币和商店之间动态取舍",
                prompt_instruction=(
                    "Use full-map route analysis. Prefer monster/elite reward density while healthy, event/rest paths while "
                    "injured, and route through shops when current gold makes a purchase likely."
                ),
                category="pathing",
                priority=7,
            ),
            Skill(
                id="team_coordination",
                name="队友协作",
                description="等待队友并根据其实际动作重新规划",
                prompt_instruction=(
                    "In multiplayer, account for teammate actions already completed this turn. Avoid duplicate lethal damage, "
                    "redundant block, or consuming shared tactical opportunities."
                ),
                category="combat",
                priority=9,
            ),
        ]
        for skill in defaults:
            self._skills[skill.id] = skill

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def enable(self, skill_id: str) -> bool:
        skill = self._skills.get(skill_id)
        if skill:
            skill.enabled = True
            return True
        return False

    def disable(self, skill_id: str) -> bool:
        skill = self._skills.get(skill_id)
        if skill:
            skill.enabled = False
            return True
        return False

    def toggle(self, skill_id: str) -> Optional[bool]:
        skill = self._skills.get(skill_id)
        if skill:
            skill.enabled = not skill.enabled
            return skill.enabled
        return None

    @property
    def enabled_skills(self) -> list[Skill]:
        return [s for s in self._skills.values() if s.enabled]

    def get_enabled_instructions(self) -> str:
        """Get the combined prompt instructions from all enabled skills."""
        instructions = []
        for skill in sorted(self.enabled_skills, key=lambda s: -s.priority):
            instructions.append(f"- {skill.prompt_instruction}")
        return "\n".join(instructions)

    def get_all(self) -> list[Skill]:
        return list(self._skills.values())

    def set_preset(self, preset_name: str) -> list[str]:
        """Apply a named preset of skills."""
        for s in self._skills.values():
            s.enabled = False

        presets = {
            "balanced": ["focus_fire", "no_overkill", "adaptive_hp_trade", "deck_coherence", "adaptive_pathing", "team_coordination"],
            "aggressive": ["aggressive", "focus_fire", "no_overkill"],
            "defensive": ["block_when_attacked", "save_potions", "conserve_energy"],
            "setup": ["setup_first", "aoe_priority", "focus_fire"],
        }

        skill_ids = presets.get(preset_name, [])
        for sid in skill_ids:
            if sid in self._skills:
                self._skills[sid].enabled = True

        return skill_ids

    def list_presets(self) -> list[str]:
        return ["balanced", "aggressive", "defensive", "setup"]
