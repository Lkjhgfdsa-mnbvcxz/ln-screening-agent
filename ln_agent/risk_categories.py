"""Normalize multi-label data-provider categories without inferring legal regimes.

Provider category 'sanctions' is a screening label; source-specific legal
characterization (e.g. export controls) must come from an attributed source.
"""
from __future__ import annotations
import re

_ALIASES = {
    "sanction": "sanctions", "sanctions": "sanctions",
    "enforcement": "enforcement", "law enforcement": "enforcement",
    "pep": "pep", "politically exposed person": "pep",
    "adverse media": "adverse_media", "adverse_media": "adverse_media",
    "other": "other",
}

def risk_categories(raw: str) -> tuple[str, ...]:
    parts = re.split(r"[,，、;/|]+", str(raw or ""))
    found: list[str] = []
    for item in parts:
        token = " ".join(item.casefold().split()).replace("-", " ")
        if not token:
            continue
        cat = _ALIASES.get(token,token.replace(" ", "_"))
        if cat not in found:
            found.append(cat)
    return tuple(found) or ("other",)

def any_category(raw: str, permitted: frozenset[str] | set[str]) -> bool:
    return not set(risk_categories(raw)).isdisjoint(permitted)
