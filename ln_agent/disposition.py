"""Evidence-grounded, concise business disposition writer.

Drafts only: never sends a compliance message, decides merchant admission,
whitelists a hit, or fabricates an offence/source.  Identity resolution and
risk priority are separate axes. All case examples are synthetic.
"""
from __future__ import annotations
from typing import Any
import re
from .evidence import norm
from .final_indicator import derive_final_indicator
from .plain_language import build_plain_summary
from .models import Case, Subject, Hit, EvidenceResult
from .policy import Policy
from .risk_categories import risk_categories, any_category

CATEGORY_CN = {
    "sanctions": "制裁", "enforcement": "执法", "pep": "PEP",
    "adverse_media": "负面新闻", "other": "其他"
}


def _singleline(value: Any, limit: int = 240) -> str:
    """Strip newlines and delimiters in external text, never execute it."""
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _first(facts, field):
    return next((f for f in facts if f.field == field and f.value), None)


def _identity_signals(subject: Subject, hit: Hit, evidence: EvidenceResult,
                      hit_facts: list | None = None) -> tuple[list[str], list[str]]:
    # Use ALL facts known at disposition time, including facts acquired during
    # bounded research. Using only hit.facts hides the decisive difference when
    # e.g. a DOB conflict was discovered by an authorized source adapter.
    current_facts = hit.facts if hit_facts is None else hit_facts
    matches: list[str] = []
    differences: list[str] = []
    rules = set(evidence.linked_rules)
    if "DOCUMENT_EXACT_MATCH" in rules:
        matches.append("证件号码一致")
    if "COMPANY_REGISTRATION_MATCH" in rules:
        matches.append("企业注册号一致")
    if "DOB_EXACT_MATCH" in rules:
        matches.append("出生日期一致")
    if "name_exact" in evidence.soft_signals:
        matches.insert(0, "企业名称一致" if hit.entity_type == "company" else "姓名一致")
    for kind, caption in (("registered_address", "注册地址"), ("residential_address", "居住地址"),
                          ("address", "地址")):
        a, b = _first(subject.facts, kind), _first(current_facts, kind)
        if not a or not b or a.context != b.context or not a.context:
            continue
        if norm(a.value) != norm(b.value):
            # Field 'address' is generic; its explicit context determines type.
            semantic_label = ("注册地址" if a.context == "REGISTERED_ADDRESS" else
                              "居住地址" if a.context == "RESIDENTIAL_ADDRESS" else caption)
            differences.append(f"{semantic_label}不一致")
            break
    if "DOB_EXACT_CONFLICT" in evidence.exclusion_rules:
        a, b = _first(subject.facts, "dob"), _first(current_facts, "dob")
        if a and b:
            differences.append(f"出生日期不同（入网{a.value}，LN {b.value}）")
    if "DOCUMENT_DIFFERENCE_NEEDS_HISTORY_VERIFICATION" in evidence.data_issues:
        differences.append("证件号码存在差异，需核实证件历史")
    return matches, differences


def _risk_event(hit: Hit) -> tuple[str, str, list[str]]:
    """A source reference is required before a free-text claim can be quoted.

    Source_ref means *attributed to the supplied record*, NOT independently
    authenticated. Therefore the draft always says 'LN记录载明'.
    """
    event = hit.risk_event or {}
    if not event.get("source_ref"):
        return "", "", []
    summary = _singleline(event.get("summary"), 1000)
    if not summary:
        return "", "", []
    refs = [_singleline(event["source_ref"], 180)]
    for item in event.get("material_context", []):
        if isinstance(item, dict) and item.get("evidence_id") and item.get("text"):
            refs.append(_singleline(item["evidence_id"], 180))
    return summary, _singleline(event.get("severity"), 20), list(dict.fromkeys(refs))


def build_disposition(*, case: Case, subject: Subject, hit: Hit,
                      evidence: EvidenceResult, route: str, identity: str,
                      suspicion: dict | None, policy: Policy, gate: dict,
                      evidence_refs: list[str],
                      hit_facts: list | None = None) -> dict:
    """Generate concise drafts from existing deterministic findings only."""
    # Include facts acquired during bounded research; using only hit.facts would
    # hide a DOB conflict discovered by an authorized source adapter.
    current_facts = hit.facts if hit_facts is None else hit_facts
    matches, differences = _identity_signals(subject, hit, evidence, current_facts)
    risk_summary, severity, event_refs = _risk_event(hit)
    # Preserve all provider labels; they are not themselves the legal source's regime.
    risk_type = "/".join(dict.fromkeys(CATEGORY_CN.get(c, c) for c in risk_categories(hit.category)))
    strong_link = identity == "strong_link"
    candidate_exclusion = identity == "excluded_candidate"
    has_name = "name_exact" in evidence.soft_signals
    serious = severity in policy.reportable_impact_levels and bool(event_refs)
    supported_category = any_category(hit.category, policy.reportable_risk_categories)
    sufficient_score = bool((suspicion or {}).get("evidence_sufficiency", {}).get("sufficient_for_numeric_score"))
    high_suspicion = bool(sufficient_score and suspicion is not None and
                          isinstance(suspicion.get("score"), (int, float)) and
                          suspicion["score"] >= policy.suspicion_report_threshold)
    # A critical, source-attributed event plus an exact entity-name link is
    # potentially reportable even when ordinary identity scoring is insufficient.
    material_weak_link = bool(serious and has_name and policy.report_critical_name_matches and
                              severity == "critical" and supported_category)
    mandatory = bool(gate.get("compliance_escalation_required"))
    # Unresolved source conflicts never become proof of a confirmed hit.
    report = bool(mandatory or (supported_category and (
        strong_link or (not candidate_exclusion and (high_suspicion or material_weak_link)))))
    if candidate_exclusion and not mandatory:
        recommendation = "EXCLUSION_CANDIDATE"
    elif report:
        recommendation = "SUSPECTED_HIT_REPORT_DRAFT"
    elif route in {"FACT_VERIFICATION_REVIEW", "FACT_CORROBORATION_REVIEW", "EVIDENCE_CONFLICT_REVIEW"}:
        recommendation = "UNRESOLVED_EVIDENCE_CHECK"
    elif route in {"POLICY_BLOCKED_REVIEW", "TOOL_FAILURE_REVIEW"}:
        recommendation = "TECHNICAL_OR_POLICY_HOLD"
    else:
        recommendation = "INSUFFICIENT_EVIDENCE_RECORDED"

    # These are the ONLY business conclusion labels. None is intentionally
    # non-conclusive: an unresolved, blocked or source-conflicted identity may
    # not be silently reclassified as 未命中. All conclusions are DRAFTS until
    # an authorised disposition workflow explicitly accepts them.
    if candidate_exclusion and not mandatory:
        business_conclusion = "未命中"
    elif strong_link and not candidate_exclusion:
        business_conclusion = "命中"
    elif report and not candidate_exclusion:
        business_conclusion = "疑似命中"
    else:
        business_conclusion = None

    # v0.9.6: the final indicator is a DERIVED TRIAGE METRIC. It is computed
    # strictly after the disposition above and cannot change any of its fields.
    # It resolves the business-facing "无结论" bucket into an explicit review
    # priority: 命中 / 疑似命中 / 误报·未命中, without clearing or reporting.
    indicator = derive_final_indicator(
        subject=subject, hit=hit, evidence=evidence, identity=identity,
        route=route, recommendation=recommendation, policy=policy, gate=gate,
        business_conclusion=business_conclusion, report_recommended=report,
        hit_facts=current_facts)

    anchor_refs = list(dict.fromkeys([x for x in evidence_refs if x] + event_refs))
    parts = matches[:3] + differences[:2]
    facts_sentence = "，".join(parts) if parts else "现有身份信息不足以确认关联"
    # Compose from verified comparison labels; free-form claims are source-attributed.
    if recommendation == "EXCLUSION_CANDIDATE":
        internal = f"未命中【{risk_type}】：{facts_sentence}；排除依据待确认。"
    elif recommendation == "SUSPECTED_HIT_REPORT_DRAFT":
        if candidate_exclusion and mandatory:
            internal = (f"【{risk_type}】需合规复核：{facts_sentence}；已有排除候选证据，"
                        "但当前上报政策仍要求复核，不代表确认命中。")
        else:
            # An exact registry/document match supports stronger wording;
            # otherwise the message must explicitly remain a suspicion.
            lead = "命中" if business_conclusion == "命中" else "疑似命中"
            internal = f"{lead}【{risk_type}】：{facts_sentence}。"
            if risk_summary:
                internal += f"事由：{risk_summary.rstrip('。；;')}。"
            else:
                internal += "名单事由待补充来源说明。"
            if not strong_link and not sufficient_score:
                internal += "身份关联尚未确认。"
    elif recommendation == "UNRESOLVED_EVIDENCE_CHECK":
        internal = f"【{risk_type}】身份待核实：{facts_sentence}；已有资料存在未核实或矛盾项。"
    elif recommendation == "TECHNICAL_OR_POLICY_HOLD":
        internal = f"【{risk_type}】核验未完成：工具或政策约束阻止进一步处理；不得视为误报。"
    else:
        internal = (f"【{risk_type}】证据不足，无法确定是否命中：{facts_sentence}；"
                    "命中记录未提供可与入网主体比对的独立身份字段，不可据此判为未命中。")

    # Optional material context is only inserted when backed by an explicit
    # evidence_id. Never infer address changes or wrongdoing from name alone.
    # It must also appear on non-conclusive drafts: otherwise 150+ unresolved
    # hits all collapse into one identical, unusable sentence. This changes
    # wording only; conclusion / recommendation / rules are unaffected.
    context_parts = [_singleline(c.get("text"), 75) for c in (hit.risk_event or {}).get("material_context", [])
                     if isinstance(c, dict) and c.get("evidence_id") and c.get("text") and risk_summary]
    if recommendation == "SUSPECTED_HIT_REPORT_DRAFT" and context_parts:
        internal += "补充：" + "；".join(context_parts[:2]) + "。"
    elif recommendation in {"INSUFFICIENT_EVIDENCE_RECORDED", "UNRESOLVED_EVIDENCE_CHECK",
                            "TECHNICAL_OR_POLICY_HOLD"} and context_parts:
        internal += "补充：" + "；".join(context_parts[:3]) + "。"

    internal = _singleline(internal, 900)
    subject_name = (_first(subject.facts, "company_name") or _first(subject.facts, "name"))
    entity_label = _singleline(subject_name.value, 100) if subject_name else _singleline(subject.subject_id)
    case_ref = _singleline(case.context.get("application_ref") or case.case_id, 130)
    review_url = _singleline(hit.screening_url, 500)
    if not review_url.startswith(("https://", "http://")):
        review_url = ""
    report_message = ""
    if report:
        report_message = f"{case_ref}｜{entity_label}\n{internal}\n辛苦老师复核查看，谢谢。"
        if review_url:
            report_message += f"\n复核链接：{review_url}"
    # v0.9.7: display-only plain-language account. Computed LAST, after every
    # decision field above is final; it reads existing values and changes none.
    plain = build_plain_summary(
        subject=subject, hit=hit, evidence=evidence, identity=identity,
        business_conclusion=business_conclusion,
        final_indicator=indicator["final_indicator"],
        final_indicator_rule=indicator["final_indicator_rule"],
        final_indicator_basis=indicator["final_indicator_basis"],
        recommendation=recommendation, report_recommended=report,
        hit_facts=current_facts, source_refs=anchor_refs)
    # Draft recommendation isn't an automatic report or a manual research queue.
    return {
        "recommendation": recommendation,  # legacy technical disposition path
        "business_conclusion": business_conclusion,
        "business_conclusion_status": "DRAFT_NOT_APPROVED" if business_conclusion else "NO_CONCLUSION",
        "conclusion_source": "AGENT_EVIDENCE_RULES",
        "identity_status": identity,
        "report_recommended": report,
        "manual_queue_required": any_category(hit.category, policy.mandatory_human_queue_categories),
        "compliance_escalation_required_by_policy": mandatory,
        "automatically_sent": False,
        "automatically_cleared": False,
        "investigation_complete": route in {"EXCLUSION_CANDIDATE", "LINKED_RISK_REVIEW", "RESIDUAL_SUSPICION"},
        "internal_note": internal,
        "compliance_message": report_message,
        "source_refs": anchor_refs,
        "attribution": "LN风险事由来自输入的来源标识；尚未独立核实" if risk_summary else "未提供可引用的风险事由来源",
        "policy_status": "候选上报规则未经公司批准；不自动发送、放行或关闭 LN 工单",
        **indicator,
        "plain_summary": plain,
    }
