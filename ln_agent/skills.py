"""Compatibility facade over actual, versioned local Skill contracts.

The JSON contracts under /skills are the runtime source of truth. This module
only preserves the original public get_skill/ordered_queries interface.
"""
from __future__ import annotations
from .skill_catalog import PRIMARY, load_skill, select_skills

SKILLS = {k: load_skill(v) for k, v in PRIMARY.items()}

def get_skill(entity_type: str) -> dict:
    if entity_type not in PRIMARY:
        raise ValueError(f"unrecognized skill entity_type: {entity_type}")
    # Reload on invocation so a trusted local contract change influences runtime.
    return load_skill(PRIMARY[entity_type])

def ordered_queries(skill: dict, keys: list[str]) -> list[str]:
    priority=skill["preferred_sources"]
    return sorted(keys, key=lambda key: priority.index(key.split(":", 1)[0])
                  if key.split(":", 1)[0] in priority else len(priority))
