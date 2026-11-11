"""Read-only imported prior decisions; never used as proof of identity.

A prior reviewer conclusion is an existing workflow state, not an independently
validated Fact. Explicit links and provenance must be preserved; no silent
replacement of historical decisions or approval authority.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

_ALLOWED = {"true_hit", "false_positive", "suspected_hit", "inconclusive"}

@dataclass(frozen=True)
class PriorDisposition:
    case_id: str
    hit_id: str
    conclusion: str
    reported: bool | None
    recorded_at: str
    source_ref: str
    reviewer_label: str = ""
    verified_by_authorized_adapter: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PriorDisposition":
        values = {key: raw.get(key) for key in
                  ("case_id", "hit_id", "conclusion", "reported", "recorded_at",
                   "source_ref", "reviewer_label", "verified_by_authorized_adapter")}
        if values["conclusion"] not in _ALLOWED:
            raise ValueError("unknown imported conclusion")
        if not all(isinstance(values[k], str) and values[k].strip()
                   for k in ("case_id", "hit_id", "recorded_at", "source_ref")):
            raise ValueError("prior decision requires case/hit, time and source")
        if values["reported"] is not None and not isinstance(values["reported"], bool):
            raise ValueError("prior reported must be boolean or null")
        # Never allow the input JSON to award itself authoritative source status.
        values["verified_by_authorized_adapter"] = False
        values["reviewer_label"] = str(values["reviewer_label"] or "")[:100]
        return cls(**values)

    def to_dict(self) -> dict:
        return asdict(self)


def compare_prior(prior: PriorDisposition, agent_decision: dict) -> dict:
    route = agent_decision.get("route")
    if prior.conclusion == "true_hit" and route == "EXCLUSION_CANDIDATE":
        comparison = "POTENTIAL_CONFLICT_REQUIRES_SOURCE_RECHECK"
    elif prior.conclusion == "false_positive" and route == "LINKED_RISK_REVIEW":
        comparison = "POTENTIAL_CONFLICT_REQUIRES_SOURCE_RECHECK"
    elif prior.conclusion == "true_hit" and route == "LINKED_RISK_REVIEW":
        comparison = "DIRECTIONALLY_CONSISTENT"
    elif prior.conclusion == "false_positive" and route == "EXCLUSION_CANDIDATE":
        comparison = "DIRECTIONALLY_CONSISTENT"
    else:
        comparison = "NOT_COMPARABLE_OR_UNRESOLVED"
    return {"prior": prior.to_dict(), "comparison": comparison,
            "agent_route": route, "agent_is_independent": True,
            "prior_status": "IMPORTED_UNVERIFIED",
            "note": "Historical decision preserved for comparison; never treated as verified identity evidence or authorization."}
