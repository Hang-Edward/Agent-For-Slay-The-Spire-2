"""Load skills from YAML configuration files."""

from __future__ import annotations

import os
from typing import Optional

from .model import SkillsRegistry, Skill


def load_skills_from_config(config_path: str) -> SkillsRegistry:
    """Load skills from a YAML config file, merging with defaults."""
    import yaml

    registry = SkillsRegistry()

    if not os.path.exists(config_path):
        return registry

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        return registry

    # Apply strategy preset
    strategy = data.get("strategy", {})
    preset = strategy.get("preset", "balanced")

    # Apply preset first
    registry.set_preset(preset)

    # Then apply individual skill toggles
    skills_config = strategy.get("skills", {})
    for skill_id, enabled in skills_config.items():
        if enabled:
            registry.enable(skill_id)
        else:
            registry.disable(skill_id)

    # Load custom skills
    custom_skills = data.get("custom_skills", {})
    for skill_id, skill_data in custom_skills.items():
        if isinstance(skill_data, dict):
            skill = Skill.from_dict({"id": skill_id, **skill_data})
            # Add to registry, potentially overriding default
            registry._skills[skill_id] = skill
            if skill.enabled:
                registry.enable(skill_id)

    return registry
