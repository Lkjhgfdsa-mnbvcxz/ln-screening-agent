"""WorkBuddy P01-P10 specifications integrated as executable, auditable findings.

Single source of truth for disabling a rule. Original comparison remains V0.5
`evidence.evaluate` and cannot be bypassed by this registry.
"""
from __future__ import annotations
from dataclasses import dataclass
from dataclasses import asdict
from ..models import EvidenceResult
from ..policy import Policy

@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    input_fields: tuple[str, ...]
    trigger: str
    evidence_requirements: str
    output: str
    prohibited_inferences: str
    next_action: str
    authority: str = "proposed"

SPECS = (
    RuleSpec("P01_NAME", ("name",), "normalized name equal", "original name fields", "SOFT_LINK", "name alone never proves identity", "compare other identifiers"),
    RuleSpec("P02_COMPLETE_DOB", ("dob",), "full valid dates equal/different", "reliable and compatible dates", "EXCLUSION_OR_LINK_CANDIDATE", "year or incomplete date not hard", "check provenance"),
    RuleSpec("P03_FULL_ID", ("document_number",), "complete namespace-matched ID", "unmasked typed complete IDs", "LINK_OR_HISTORY_CHECK", "different IDs do not prove different people", "check issue history"),
    RuleSpec("P04_TEMPORAL_IMPOSSIBILITY", ("dob", "acted_in_year"), "recorded event before birth", "explicit qualified action time", "EXCLUSION_CANDIDATE", "article publication time is not action time", "verify event identity"),
    RuleSpec("P05_GENDER", ("gender",), "gender differs", "same field meaning and source", "SOFT_REVIEW", "gender difference alone cannot exclude", "check documents"),
    RuleSpec("P06_REGION_ADDRESS", ("region", "address"), "location match", "address type and usage period", "SOFT_ONLY", "residence and registered address are distinct", "verify actual address relation"),
    RuleSpec("P07_CAREER", ("employer", "role", "company_name"), "career connection", "organization and date context", "SOFT_ONLY", "do not infer age from seniority", "find dated official roles"),
    RuleSpec("P08_COMPANY_ID", ("registration_number",), "complete registry ID equal", "same jurisdiction and registry namespace", "STRONG_LINK_CANDIDATE", "same company name or address alone insufficient", "confirm entity identity"),
    RuleSpec("P09_SOURCE_CONFLICT", ("dob", "document_number"), "multiple incompatible reliable facts", "sources and applicable person", "CONFLICT_REVIEW", "cannot quietly select favorable source", "reconcile source"),
    RuleSpec("P10_PHOTO_EVENT", ("photo_comparison", "acted_in_year"), "photo or event lead", "proven individual correspondence", "SOFT_ONLY", "appearance never hard exclusion", "human source review"),
)
RULE_MAP = {
    "P01_NAME": ((), (), ("name_exact",)),
    "P02_COMPLETE_DOB": (("DOB_EXACT_CONFLICT",), ("DOB_EXACT_MATCH",), ("dob_exact",)),
    "P03_FULL_ID": ((), ("DOCUMENT_EXACT_MATCH",), ("document_difference_verify_history",)),
    "P04_TEMPORAL_IMPOSSIBILITY": (("PRE_BIRTH_ACTION_IMPOSSIBLE",), (), ()),
    "P05_GENDER": ((), (), ("gender_difference_review",)),
    "P06_REGION_ADDRESS": ((), (), ("region_overlap", "address_overlap")),
    "P07_CAREER": ((), (), ("company_link", "role_overlap")),
    "P08_COMPANY_ID": ((), ("COMPANY_REGISTRATION_MATCH",), ()),
    "P09_SOURCE_CONFLICT": ((), (), ()),
    "P10_PHOTO_EVENT": ((), (), ("photo_difference_human_only",)),
}

class RuleRegistry:
    def __init__(self, policy: Policy):
        self.policy = policy
        self.rules = {spec.rule_id: spec for spec in SPECS}

    def filter_and_find(self, evidence: EvidenceResult) -> tuple[EvidenceResult, list[dict]]:
        r = EvidenceResult(exclusion_rules=list(evidence.exclusion_rules), linked_rules=list(evidence.linked_rules),
            soft_signals=list(evidence.soft_signals), data_issues=list(evidence.data_issues), anchors=list(evidence.anchors))
        findings = []
        for spec in SPECS:
            exclusions, links, signals = RULE_MAP[spec.rule_id]
            if spec.rule_id in self.policy.disabled_rules:
                r.exclusion_rules = [v for v in r.exclusion_rules if v not in exclusions]
                r.linked_rules = [v for v in r.linked_rules if v not in links]
                r.soft_signals = [v for v in r.soft_signals if v not in signals]
                if spec.rule_id == "P03_FULL_ID":
                    r.data_issues = [x for x in r.data_issues if x != "DOCUMENT_DIFFERENCE_NEEDS_HISTORY_VERIFICATION"]
                if spec.rule_id == "P09_SOURCE_CONFLICT":
                    # Safety invariant: disabling a policy rule CANNOT suppress source data conflicts.
                    pass
                continue
            matched = [x for x in r.exclusion_rules if x in exclusions] + [x for x in r.linked_rules if x in links] + [x for x in r.soft_signals if x in signals]
            if spec.rule_id == "P09_SOURCE_CONFLICT":
                matched += r.data_issues
            if matched:
                findings.append({"rule_id": spec.rule_id, "authority": spec.authority, "matches": list(matched),
                                 "output": spec.output, "prohibited_inferences": spec.prohibited_inferences,
                                 "requires_review": True})
        return r, findings

    def coverage(self) -> dict:
        return {"total": len(SPECS), "enabled": len([x for x in SPECS if x.rule_id not in self.policy.disabled_rules]),
                "company_approved": 0, "specifications_complete": all(all((x.input_fields, x.trigger, x.evidence_requirements, x.output, x.prohibited_inferences, x.next_action)) for x in SPECS)}
