"""V0.5 independent-source corroboration of *human-attested* document facts.

Same publisher or a mirrored article is not by itself evidence of independent
origin. No unreviewed LLM claim enters this module. A trusted review must bind
both an event claim_id and a checked source_origin_id; distinct source documents
with an identical original origin are counted only once. This module does not
make identity or regulatory disposition decisions.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class CorroborationFinding:
    case_id: str
    hit_id: str
    claim_id: str
    field: str
    status: str  # CORROBORATED, SINGLE_SOURCE, CONTRADICTORY_SOURCES, LINEAGE_UNVERIFIED
    independent_groups: int
    values: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    source_origins: tuple[str, ...]
    verification_ids: tuple[str, ...]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_corroboration(*, case_id: str, hit_id: str,
                         records: list[dict[str, Any]],
                         minimum_independent_sources: int = 2) -> list[CorroborationFinding]:
    """Report only. A value agreement is never a substitute for entity attribution.

    Records are emitted by trusted FactVerifier, not direct document candidates.
    Different claim IDs are different events even if they have the same name.
    """
    if minimum_independent_sources < 2:
        raise ValueError("independent-source minimum must be >=2")
    by_claim: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in records:
        if (r.get("case_id"), r.get("hit_id")) != (case_id, hit_id):
            continue
        if r.get("status") != "VERIFIED_FOR_COMPARISON" or not r.get("verification_id"):
            continue
        claim_id = r.get("claim_id")
        if not claim_id:
            continue  # No fabricated event attribution from matching words/year.
        by_claim[(claim_id, r.get("field", ""))].append(r)
    findings = []
    for (claim, field), items in sorted(by_claim.items()):
        all_values = tuple(sorted({str(r["value"]) for r in items}))
        evidence_ids = tuple(sorted({r["evidence_id"] for r in items}))
        verifications = tuple(sorted({r["verification_id"] for r in items}))
        verified_origins = {str(r["source_origin_id"]) for r in items
                            if r.get("source_independence_checked") and r.get("source_origin_id")}
        all_lineages_checked = all(r.get("source_independence_checked") and r.get("source_origin_id")
                                   for r in items)
        # Conflicting verified statements on the same specifically reviewed event
        # must be investigated before any confidence boost.
        if len(all_values) > 1:
            status, explanation = ("CONTRADICTORY_SOURCES",
                "经人工绑定到同一事件的来源给出不同事实；必须先核对，禁止据此确认或排除。")
        elif not all_lineages_checked:
            status, explanation = ("LINEAGE_UNVERIFIED",
                "尚未逐一核验原始来源谱系；不同链接或转载不等于独立佐证。")
        elif len(verified_origins) >= minimum_independent_sources:
            status, explanation = ("CORROBORATED",
                "达到声明的独立来源数量；仍受人物归属、来源质量和处置政策约束。")
        else:
            status, explanation = ("SINGLE_SOURCE",
                "独立原始来源不足；同源转载/同文档重复引用不重复计数。")
        findings.append(CorroborationFinding(case_id, hit_id, claim, field, status,
            len(verified_origins), all_values, evidence_ids,
            tuple(sorted(verified_origins)), verifications, explanation))
    return findings
