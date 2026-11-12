"""Deterministic final triage indicator (v0.9.6).

IMPORTANT — this is a DOWNSTREAM, READ-ONLY DERIVED METRIC.

It consumes *only* facts and rule outputs that the existing pipeline already
produced (Rule Engine -> PolicyGuard -> Decision Router -> Disposition).  It
never changes ``business_conclusion``, ``recommendation``, ``route``, rule
findings or gate state; it never asks a model to invent a reason; and it never
sends a report, clears/whitelists a hit, closes a checklist or opens a manual
research queue.  ``误报·未命中`` is a *review-priority / statistics* label, not
an exclusion decision: ``does_not_clear_hit`` is always True.

Three labels, mirroring the business rule requested by reviewers:

FI-1 命中          hard identity match / confirmed strong link.
FI-2 疑似命中      serious, source-attributed event AND consistent incident
                   location; or an existing report draft / mandatory escalation;
                   or a source conflict / policy block that may not be cleared.
FI-3 误报·未命中   no material risk information, e.g. identity fields that only
                   the notice carries cannot be obtained and nothing serious is
                   attached to the hit.  Grouped with 未命中 for statistics only.

All outputs are DRAFTS until an authorised disposition workflow accepts them.
"""
from __future__ import annotations

from typing import Any, Iterable

from .evidence import norm
from .models import EvidenceResult, Hit, Subject
from .policy import Policy

INDICATOR_LABELS: tuple[str, ...] = ("命中", "疑似命中", "误报·未命中")
RULE_IDS = {"命中": "FI-1", "疑似命中": "FI-2", "误报·未命中": "FI-3"}
SEVERITY_ORDER = {"误报·未命中": 1, "疑似命中": 2, "命中": 3}

HARD_MATCH_RULES = ("DOCUMENT_EXACT_MATCH", "COMPANY_REGISTRATION_MATCH", "DOB_EXACT_MATCH")
IDENTITY_FIELDS = ("document_number", "dob", "registration_number")
LOCATION_FIELDS = ("region", "jurisdiction", "country", "nationality",
                   "registered_address", "residential_address", "address")
EVENT_REGION_KEYS = ("event_region", "incident_region", "event_country",
                     "event_location", "jurisdiction")
MASK_CHARS = set("*xX•")
BLOCKED_ROUTES = frozenset({"POLICY_BLOCKED_REVIEW", "TOOL_FAILURE_REVIEW"})
CONFLICT_ROUTES = frozenset({"EVIDENCE_CONFLICT_REVIEW", "FACT_VERIFICATION_REVIEW",
                             "FACT_CORROBORATION_REVIEW"})


def _clean(value: Any) -> str:
    return norm(str(value or "").strip())


def _masked(value: Any) -> bool:
    text = str(value or "")
    return not text.strip() or any(ch in MASK_CHARS for ch in text)


def _field(fact: Any) -> str:
    return str(fact.get("field", "")) if isinstance(fact, dict) else str(getattr(fact, "field", ""))


def _value(fact: Any) -> str:
    return str(fact.get("value", "")) if isinstance(fact, dict) else str(getattr(fact, "value", ""))


def _fact_values(facts: Iterable[Any], fields: Iterable[str]) -> list[tuple[str, str]]:
    wanted = set(fields)
    out: list[tuple[str, str]] = []
    for fact in facts or []:
        field = _field(fact)
        if field not in wanted or _masked(_value(fact)):
            continue
        cleaned = _clean(_value(fact))
        if cleaned:
            out.append((field, cleaned))
    return out


def _event_signals(hit: Hit) -> tuple[str, str, list[str]]:
    """Mirror disposition's source-attribution rule without importing it.

    A free-text risk claim is only usable when the hit carries an explicit
    source_ref.  ``source_ref`` means *attributed to the supplied record*, not
    independently authenticated.
    """
    event = hit.risk_event or {}
    if not event.get("source_ref"):
        return "", "", []
    summary = str(event.get("summary") or "").strip()
    if not summary:
        return "", "", []
    refs = [str(event["source_ref"])]
    for item in event.get("material_context", []) or []:
        if isinstance(item, dict) and item.get("evidence_id") and item.get("text"):
            refs.append(str(item["evidence_id"]))
    return summary, str(event.get("severity") or "").strip(), list(dict.fromkeys(refs))


def _event_regions(hit: Hit) -> list[str]:
    event = hit.risk_event or {}
    raw: list[str] = []
    for key in EVENT_REGION_KEYS:
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            raw.append(value.strip())
        elif isinstance(value, (list, tuple)):
            raw.extend(str(x).strip() for x in value if str(x).strip())
    for item in event.get("material_context", []) or []:
        if not isinstance(item, dict) or not item.get("evidence_id"):
            continue
        for key in ("region", "place", "location", "event_region"):
            if item.get(key):
                raw.append(str(item[key]).strip())
    return [v for v in (_clean(x) for x in raw) if v]


def _location_consistency(subject: Subject, hit_facts: Iterable[Any],
                          hit: Hit) -> tuple[bool, list[str]]:
    """Deterministic '事发地一致' check — never inferred from a name or a model.

    Consistency requires an exact normalised match between an explicit incident
    location and the applicant / hit location, or between the applicant and hit
    locations themselves.  Missing values are UNKNOWN, never 'consistent'.
    """
    event_regions = set(_event_regions(hit))
    applicant = _fact_values(subject.facts, LOCATION_FIELDS)
    hit_values = _fact_values(hit_facts, LOCATION_FIELDS)
    applicant_set = {v for _, v in applicant}
    hit_set = {v for _, v in hit_values}

    consistent = bool(applicant_set & (hit_set | event_regions)) or bool(event_regions & hit_set)
    basis: list[str] = []
    if event_regions:
        basis.append("名单载明事发地 " + "/".join(sorted(event_regions)[:2]))
    if applicant:
        basis.append("入网主体地区 " + "/".join(v for _, v in applicant[:2]))
    if consistent:
        basis.append("事发地与主体/记录所在地一致（结构化字段精确匹配）")
    elif event_regions or applicant_set or hit_set:
        basis.append("事发地未形成一致匹配（或仅单侧有值，视为未知）")
    else:
        basis.append("无可用事发地字段，视为未知")
    return consistent, basis


def _identity_available(hit_facts: Iterable[Any]) -> tuple[bool, list[str]]:
    found = [f for f, _ in _fact_values(hit_facts, IDENTITY_FIELDS)]
    return bool(found), found


def derive_final_indicator(*, subject: Subject, hit: Hit, evidence: EvidenceResult,
                           identity: str, route: str, recommendation: str,
                           policy: Policy, gate: dict, business_conclusion: str | None,
                           report_recommended: bool,
                           hit_facts: Iterable[Any]) -> dict[str, Any]:
    """Derive the triage indicator from existing deterministic outputs only."""
    facts = list(hit_facts or [])
    linked = set(evidence.linked_rules or [])
    exclusion = set(evidence.exclusion_rules or [])
    hard = [r for r in HARD_MATCH_RULES if r in linked]

    _, severity, event_refs = _event_signals(hit)
    serious = severity in policy.reportable_impact_levels and bool(event_refs)
    location_ok, location_basis = _location_consistency(subject, facts, hit)
    identity_ok, identity_fields = _identity_available(facts)

    mandatory = bool(gate.get("compliance_escalation_required"))
    blocked = recommendation == "TECHNICAL_OR_POLICY_HOLD" or route in BLOCKED_ROUTES
    conflict = route in CONFLICT_ROUTES or bool(exclusion & {"DOB_EXACT_CONFLICT"})
    confirmed = business_conclusion == "命中" and identity == "strong_link"

    if confirmed:
        label = "命中"
    elif mandatory or report_recommended or (serious and location_ok) or blocked or conflict:
        label = "疑似命中"
    else:
        label = "误报·未命中"

    basis: list[str] = []
    if hard:
        basis.append("硬匹配规则命中：" + "、".join(hard))
    if confirmed:
        basis.append("业务结论草稿=命中，identity=strong_link")
    if serious:
        basis.append(f"名单事由等级 {severity}，可引用来源标识 {len(event_refs)} 条")
    elif severity:
        basis.append(f"名单事由等级 {severity}，未达到政策重大等级或缺少来源标识")
    else:
        basis.append("无可引用的重大名单事由")
    basis.extend(location_basis)
    if mandatory:
        basis.append("政策要求合规升级，保留复核")
    if blocked:
        basis.append("工具/政策阻断，不得归入误报，保留复核")
    if conflict:
        basis.append("来源存在冲突或未核实项，不得归入误报，保留复核")
    if identity_ok:
        basis.append("命中侧有独立身份字段：" + "、".join(dict.fromkeys(identity_fields)))
    else:
        basis.append("命中侧无可比对独立身份字段（证件号/出生日期/注册号缺失或脱敏）")
    if label == "误报·未命中":
        basis.append("无重大风险事由或事发地未形成一致匹配；仅通知层信息缺失，按误报归集（不放行）")

    return {
        "final_indicator": label,
        "final_indicator_rule": RULE_IDS[label],
        "final_indicator_basis": basis,
        "final_indicator_status": "DRAFT_NOT_APPROVED",
        "final_indicator_kind": "TRIAGE_METRIC",
        "final_indicator_does_not_clear_hit": True,
        "final_indicator_changes_business_conclusion": False,
        "final_indicator_inputs": {
            "hard_match_rules": hard,
            "severity": severity,
            "serious": serious,
            "location_consistent": location_ok,
            "identity_fields_available": identity_ok,
            "mandatory_escalation": mandatory,
            "blocked": blocked,
            "conflict": conflict,
            "business_conclusion": business_conclusion,
            "report_recommended": report_recommended,
            "route": route,
            "recommendation": recommendation,
        },
    }


def derive_case_indicator(labels: Iterable[str]) -> dict[str, Any]:
    """Roll per-hit indicators up to one checklist-level final indicator."""
    items = [x for x in labels if x in INDICATOR_LABELS]
    distribution = {k: items.count(k) for k in INDICATOR_LABELS}
    label = max((k for k in INDICATOR_LABELS if distribution[k]),
                key=lambda k: SEVERITY_ORDER[k], default="误报·未命中")
    escalation = distribution["命中"] + distribution["疑似命中"]
    return {
        "case_final_indicator": label,
        "final_indicator_distribution": distribution,
        "escalation_hits": escalation,
        "escalation_rate": round(escalation / len(items), 4) if items else 0.0,
        "note": "工单级指标取本单最高等级；仅用于统计与复核优先级，不改变任何一条命中的业务结论。",
    }
