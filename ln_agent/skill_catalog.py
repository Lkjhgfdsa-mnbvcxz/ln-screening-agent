"""Runtime skill contracts loaded from repository-level skills/*/contract.json.

Only trusted local files; neither web content nor Sub-agent output can rewrite contracts.
"""
from __future__ import annotations
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1] / "skills"
PRIMARY = {"person": "person_ln", "company": "company_ln", "address": "address_ln"}
ADDITIONAL = {"document_intelligence", "source_recovery", "residual_suspicion",
              "disposition_reporting", "workbuddy_capture"}


def load_skill(skill_slug: str, *, root: Path | None = None) -> dict:
    base = root if root is not None else ROOT
    path = base / skill_slug / "contract.json"
    if skill_slug not in set(PRIMARY.values()) | ADDITIONAL:
        raise ValueError("unknown skill: " + skill_slug)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not raw.get("id") or not raw.get("version") or not raw.get("read_only", False):
        raise ValueError("missing/unsafe Skill contract: " + skill_slug)
    if skill_slug in PRIMARY.values():
        must = ("fields", "preferred_sources", "allowed_research_sources", "blocked_exclusion_fields", "prohibited_shortcuts", "allowed_tool_names")
        if any(not raw.get(x) for x in must):
            raise ValueError("incomplete primary Skill contract: " + skill_slug)
    return raw


def select_skills(entity_type: str, research_keys: list[str] | tuple[str, ...] = (), *, phase: str = "investigation") -> list[dict]:
    if entity_type not in PRIMARY:
        raise ValueError("unknown entity type: " + entity_type)
    slugs = [PRIMARY[entity_type]]
    if any(k.startswith("doc:") for k in research_keys):
        slugs.append("document_intelligence")
    if any(k.startswith(("ln:", "official:", "web:")) for k in research_keys):
        slugs.append("source_recovery")
    if phase == "investigation" and any(k.startswith(("boss:", "model:")) for k in research_keys):
        slugs.append("workbuddy_capture")
    if phase == "suspicion":
        slugs.append("residual_suspicion")
    if phase == "disposition":
        slugs.append("disposition_reporting")
    return [load_skill(s) for s in slugs]
