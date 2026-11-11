"""Independent phase-II suspicion triage, only for unresolved subjects.

No precision score where identity evidence is insufficient. Negative factors are
shown separately and cannot magically cancel a confirmed sanctions restriction.
"""
from __future__ import annotations
from .models import EvidenceResult, Hit
from .policy import Policy

class SuspicionAgent:
    def __init__(self,policy:Policy):self.policy=policy

    def assess(self,hit:Hit,evidence:EvidenceResult)->dict:
        signals=set(evidence.soft_signals)
        if hit.category=="sanctions":signals.add("sanctions_category")
        weights=dict(self.policy.suspicion_weights)
        contributions={s:weights[s] for s in sorted(signals) if s in weights}
        # Sufficient identity info is a prerequisite; category and a generic
        # same-name signal alone do not support numerical suspicion precision.
        discriminators={"region_overlap","address_overlap","company_link","dob_exact","ongoing_pep","former_pep","recent_adverse_event"}
        independent={"region_overlap","address_overlap","company_link","dob_exact"}
        sufficient=bool(signals & independent)
        insuff_reason=None if sufficient else "缺少足以区分同名身份的独立字段；不输出精确分数"
        score=sum(contributions.values()) if sufficient else None
        negative={k:v for k,v in contributions.items() if v<0}
        if hit.category in self.policy.unresolved_mandatory_review:
            recommendation="MANDATORY_REVIEW"
        elif not sufficient:
            recommendation="INSUFFICIENT_EVIDENCE_MANUAL_ASSESSMENT"
        elif score>=self.policy.suspicion_report_threshold:
            recommendation="RECOMMEND_REPORT_FOR_REVIEW"
        elif score>=self.policy.suspicion_review_threshold:
            recommendation="MANUAL_ASSESSMENT"
        else:
            recommendation="LOWER_PRIORITY_MANUAL_ASSESSMENT"
        return {
          "score":score,"factors":contributions,"negative_factors":negative,
          "evidence_sufficiency":{"sufficient_for_numeric_score":sufficient,"reason":insuff_reason},
          "recommendation":recommendation,"identity_still_unresolved":True,
          "automatically_reported":False,"automatically_cleared":False,
          "warning":"演示权重及阈值未经校准；评分仅供人工参考，绝不自动决定上报/不上报"
        }
