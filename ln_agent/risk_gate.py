"""An independent Q0 & final gate; flags are not identity decisions.

Within a run, a triggered escalation is retained for human review. Current
policy defaults to NO mandatory compliance categories (approval required).
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from .models import Hit
from .policy import Policy
from .risk_categories import any_category, risk_categories

@dataclass(frozen=True)
class GateDecision:
    screening_alert_observed: bool
    requires_manual_screening_review: bool
    compliance_escalation_required: bool
    conditions: tuple[str, ...]
    trigger_history: tuple[dict, ...]
    escalation_policy_ref: str = "UNAPPROVED_DEMO_CONFIGURATION"

    def to_dict(self) -> dict:
        return asdict(self)

class RiskGate:
    def __init__(self, policy: Policy):
        self.policy = policy

    def evaluate(self, hit: Hit, identity_state: str, previous: list[dict] | None = None) -> GateDecision:
        history = list(previous or [])
        now = any_category(hit.category, self.policy.mandatory_compliance_categories)
        prior = any(x.get("compliance_escalation_triggered", False) for x in history)
        retained = now or prior
        conditions = ["SCREENING_ALERT_OBSERVED"]
        manual = any_category(hit.category, self.policy.unresolved_mandatory_review) or retained
        if manual:
            conditions.append("SCREENING_REVIEW_REQUIRED")
        if retained:
            conditions.append("COMPLIANCE_ESCALATION_REQUIRED")
            if prior and not now:
                conditions.append("ESCALATION_RETAINED_FROM_TRIGGER_HISTORY")
        else:
            conditions.append("ESCALATION_NOT_TRIGGERED_BY_CURRENT_POLICY")
        history.append({"identity_state": identity_state, "hit_id": hit.hit_id,
                        "category": hit.category, "category_labels": list(risk_categories(hit.category)),
                        "compliance_escalation_triggered": bool(now),
                        "compliance_escalation_retained": bool(retained)})
        return GateDecision(True, bool(manual), bool(retained), tuple(conditions), tuple(history))

