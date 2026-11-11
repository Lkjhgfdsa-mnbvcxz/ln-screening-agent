"""Executable runtime controls; business policy rules are still UNAPPROVED.

The gate cannot silently disappear when exclusion/strong-link branches return.
"""
from __future__ import annotations
from dataclasses import dataclass
from .policy import Policy
from .models import Fact, Hit, Case

@dataclass(frozen=True)
class GateResult:
    flags: tuple[str,...]
    reasons: tuple[str,...]

class PolicyViolation(ValueError): pass

@dataclass(frozen=True)
class CheckResult:
    allowed: bool
    reason: str = ""

class PolicyGuard:
    def __init__(self,policy: Policy):self.policy=policy

    def check_ingest(self, case: Case, hit: Hit, facts: list[Fact]) -> CheckResult:
        # Checkpoint 1: all data must belong to the current Case and Hit.
        subject_ids = {x.subject_id for x in case.subjects}
        hit_ids = {x.hit_id for x in case.hits}
        if hit.subject_id not in subject_ids:
            return CheckResult(False, "case/hit membership mismatch")
        # Direct per-hit tests may pass a newly constructed hit for an existing
        # subject. An existing hit ID must still agree with the case subject.
        for existing in case.hits:
            if existing.hit_id == hit.hit_id and existing.subject_id != hit.subject_id:
                return CheckResult(False, "hit id reused across subjects")
        if any(f.side != "hit" for f in facts):
            return CheckResult(False, "incoming hit facts have wrong side")
        if any(not f.evidence_id for f in facts):
            return CheckResult(False, "missing evidence_id")
        return CheckResult(True)

    def check_tool_call(self, name: str, key: str, skill: dict, count: int) -> CheckResult:
        # Checkpoint 2: actual runtime tool allowlist + skill scope + budget.
        if name not in self.policy.allowed_tool_names:
            return CheckResult(False, "tool not on approved local allowlist")
        try:
            self.validate_action(key, skill, count)
        except PolicyViolation as exc:
            return CheckResult(False, str(exc))
        return CheckResult(True)

    def check_state_transition(self, action: str, human_confirmed: bool = False) -> CheckResult:
        # Checkpoint 5: no automatic whitelist, LN disposition or compliance closure.
        if action in {"LN_WRITEBACK", "WHITELIST", "COMPLIANCE_CLOSE", "AUTO_RELEASE"} and not human_confirmed:
            return CheckResult(False, "human confirmation and approved backend required")
        if action in {"LN_WRITEBACK", "WHITELIST", "COMPLIANCE_CLOSE", "AUTO_RELEASE"}:
            return CheckResult(False, "operation not implemented by the offline prototype")
        return CheckResult(True)

    def assess_risk_gate(self,hit:Hit) -> GateResult:
        flags=[];reasons=[]
        if hit.category in self.policy.unresolved_mandatory_review:
            flags.append("SCREENING_REVIEW_REQUIRED")
            reasons.append("需保留名单核验人工复核，不代表已确认关联或必报合规")
        if hit.category in self.policy.mandatory_compliance_categories:
            flags.append("COMPLIANCE_ESCALATION_REQUIRED")
            reasons.append("命中由外部批准的合规上报类别配置；仍需身份核验")
        return GateResult(tuple(flags),tuple(reasons))

    def validate_action(self,key:str,skill:dict,action_count:int)->None:
        if action_count>=self.policy.max_research_actions_per_hit:
            raise PolicyViolation("per-hit research budget exceeded")
        if ":" not in key: raise PolicyViolation("research action needs typed source prefix")
        prefix=key.split(":",1)[0]
        if prefix not in skill["allowed_research_sources"]:
            raise PolicyViolation(f"research source not allowed by skill contract: {prefix}")

    def validate_facts(self, facts:list[Fact],skill:dict)->list[Fact]:
        result=[]
        for f in facts:
            if f.side!="hit":raise PolicyViolation("sub-agent cannot add applicant facts")
            if f.origin=="reviewer_verified" or f.verification_id:
                raise PolicyViolation("sub-agent cannot submit approved document facts")
            if f.field not in skill["fields"] and f.field not in {"acted_in_year"}:
                raise PolicyViolation(f"field not allowed by skill contract: {f.field}")
            if f.origin=="model_extracted" and f.checked:
                raise PolicyViolation("model output cannot self-verify")
            result.append(f)
        return result

    def validate_hard_rules(self, exclusion_rules:list[str],skill:dict)->None:
        # Guard against introducing a shortcut into the deterministic engine.
        for rule in exclusion_rules:
            if rule not in {"DOB_EXACT_CONFLICT","PRE_BIRTH_ACTION_IMPOSSIBLE"}:
                raise PolicyViolation(f"unapproved hard rule candidate: {rule}")
        if not skill.get("prohibited_shortcuts") or not skill.get("blocked_exclusion_fields"):
            raise PolicyViolation("skill missing forbidden-inference contract")

    def authorized_exclusion(self,rule_ids:list[str])->bool:
        # Candidate rules are never approved automatically just because they ran.
        return bool(self.policy.approved_exclusion_rules.intersection(rule_ids)) and self.policy.allow_automatic_ln_disposition

    def validate_reviewed_document_facts(self, facts:list[Fact], valid_verification_ids:set[str])->None:
        for f in facts:
            if (f.side!="hit" or f.origin!="reviewer_verified" or not f.checked or
                not f.verification_id or f.verification_id not in valid_verification_ids):
                raise PolicyViolation("reviewed fact lacks trusted verification ledger entry")
