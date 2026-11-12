"""Executable runtime controls; business policy rules are still UNAPPROVED.

The gate cannot silently disappear when exclusion/strong-link branches return.
"""
from __future__ import annotations
from dataclasses import dataclass
from .policy import Policy
from .models import Fact, Hit, Case
from .tool_catalog import available_for_call, load_tool
from .skill_catalog import load_skill
from .risk_categories import any_category

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
        ok, message = available_for_call(name, source_key=key)
        if not ok:
            return CheckResult(False, message)
        if "allowed_tool_names" in skill and name not in skill["allowed_tool_names"]:
            return CheckResult(False, "tool not allowed by selected Skill contract")
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
        if any_category(hit.category, self.policy.unresolved_mandatory_review):
            flags.append("SCREENING_REVIEW_REQUIRED")
            reasons.append("需保留名单核验人工复核，不代表已确认关联或必报合规")
        if any_category(hit.category, self.policy.mandatory_compliance_categories):
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

    def validate_facts(self, facts:list[Fact],skill:dict,*,tool_name:str|None=None)->list[Fact]:
        # Manifest-driven capability fence: a tool may only emit the origins its
        # own tool.json declares, and an unchecked-output tool cannot smuggle in
        # checked facts. This is enforced here, at the only ingestion boundary.
        spec = load_tool(tool_name) if tool_name else None
        allowed_origins = frozenset(spec.get("allowed_fact_origins", [])) if spec else None
        must_be_unchecked = bool(spec and spec.get("facts_must_be_unchecked"))
        result=[]
        for f in facts:
            if f.side!="hit":raise PolicyViolation("sub-agent cannot add applicant facts")
            if f.origin=="reviewer_verified" or f.verification_id:
                raise PolicyViolation("sub-agent cannot submit approved document facts")
            if f.field not in skill["fields"] and f.field not in {"acted_in_year"}:
                raise PolicyViolation(f"field not allowed by skill contract: {f.field}")
            if f.origin=="model_extracted" and f.checked:
                raise PolicyViolation("model output cannot self-verify")
            if allowed_origins and f.origin not in allowed_origins:
                raise PolicyViolation(f"tool {tool_name} cannot emit origin {f.origin}")
            if must_be_unchecked and f.checked:
                raise PolicyViolation(f"tool {tool_name} must emit unchecked candidates")
            result.append(f)
        return result

    def validate_hard_rules(self, exclusion_rules:list[str],skill:dict)->None:
        # Guard against introducing a shortcut into the deterministic engine.
        for rule in exclusion_rules:
            if rule not in {"DOB_EXACT_CONFLICT","PRE_BIRTH_ACTION_IMPOSSIBLE"}:
                raise PolicyViolation(f"unapproved hard rule candidate: {rule}")
        if not skill.get("prohibited_shortcuts") or not skill.get("blocked_exclusion_fields"):
            raise PolicyViolation("skill missing forbidden-inference contract")
        # This is a real policy check on the currently selected Skill contract,
        # rather than a string-only instruction in SKILL.md.
        rule_field_map = {
            "DOB_EXACT_CONFLICT": frozenset({"dob"}),
            "PRE_BIRTH_ACTION_IMPOSSIBLE": frozenset({"dob", "acted_in_year"}),
        }
        blocked = set(skill["blocked_exclusion_fields"])
        for rule in exclusion_rules:
            if rule_field_map[rule] & blocked:
                raise PolicyViolation(f"Skill blocks a hard-rule field: {rule}")

    def authorized_exclusion(self,rule_ids:list[str])->bool:
        # Candidate rules are never approved automatically just because they ran.
        return bool(self.policy.approved_exclusion_rules.intersection(rule_ids)) and self.policy.allow_automatic_ln_disposition

    def validate_reviewed_document_facts(self, facts:list[Fact], valid_verification_ids:set[str])->None:
        for f in facts:
            if (f.side!="hit" or f.origin!="reviewer_verified" or not f.checked or
                not f.verification_id or f.verification_id not in valid_verification_ids):
                raise PolicyViolation("reviewed fact lacks trusted verification ledger entry")

    def validate_disposition_draft(self, disposition: dict) -> None:
        """Enforce machine contract at the actual disposition-output boundary."""
        skill = load_skill("disposition_reporting")
        tool = load_tool("disposition_writer")
        if tool["status"] != "implemented_internal" or tool["writes_external"] is not False:
            raise PolicyViolation("disposition tool unavailable or unsafe")
        for key in skill["required_output_fields"]:
            if key not in disposition:
                raise PolicyViolation(f"disposition missing required field: {key}")
        business = disposition.get("business_conclusion")
        if business not in {None, "未命中", "疑似命中", "命中"}:
            raise PolicyViolation("business conclusion must be one of exactly three labels or null")
        if disposition.get("business_conclusion_status") != (
            "DRAFT_NOT_APPROVED" if business else "NO_CONCLUSION"
        ):
            raise PolicyViolation("business conclusion must carry its draft/unresolved state")
        if business == "未命中" and disposition.get("recommendation") != "EXCLUSION_CANDIDATE":
            raise PolicyViolation("unverified no-hit conclusion")
        if business == "命中" and disposition.get("identity_status") != "strong_link":
            raise PolicyViolation("unverified confirmed-hit conclusion")
        if business == "疑似命中" and not disposition.get("report_recommended"):
            raise PolicyViolation("suspected hit requires supported report recommendation")
        # v0.9.6 derived triage metric: downstream only, never a new disposition.
        metric = skill.get("derived_metric", {})
        indicator = disposition.get("final_indicator")
        if indicator not in metric.get("allowed_labels", []):
            raise PolicyViolation("final indicator must be one of the approved triage labels")
        if disposition.get("final_indicator_rule") not in metric.get("rules", []):
            raise PolicyViolation("final indicator missing its deterministic rule id")
        if disposition.get("final_indicator_status") != "DRAFT_NOT_APPROVED":
            raise PolicyViolation("final indicator must remain an unapproved draft")
        if disposition.get("final_indicator_kind") != metric.get("kind"):
            raise PolicyViolation("final indicator must be declared a triage metric")
        if disposition.get("final_indicator_does_not_clear_hit") is not True:
            raise PolicyViolation("final indicator may never clear or whitelist a hit")
        if disposition.get("final_indicator_changes_business_conclusion") is not False:
            raise PolicyViolation("final indicator may not rewrite the business conclusion")
        basis = disposition.get("final_indicator_basis")
        if not isinstance(basis, list) or not basis or not all(isinstance(x, str) and x for x in basis):
            raise PolicyViolation("final indicator requires deterministic evidence basis")
        if indicator == "命中" and business != "命中":
            raise PolicyViolation("final indicator may not upgrade an unconfirmed hit")
        if indicator == "误报·未命中" and (business in {"命中", "疑似命中"} or
                                    disposition.get("report_recommended") or
                                    disposition.get("identity_status") == "strong_link"):
            raise PolicyViolation("false-positive grouping may not downgrade a confirmed/suspected hit")
        if not isinstance(disposition["internal_note"], str) or not disposition["internal_note"].strip():
            raise PolicyViolation("disposition requires concise internal note")
        if disposition.get("automatically_sent") or disposition.get("automatically_cleared"):
            raise PolicyViolation("automatic report transmission or clearance is forbidden")
        if disposition.get("attribution", "").startswith("LN风险事由") and not disposition.get("source_refs"):
            raise PolicyViolation("source-attributed risk statement missing source references")
        if disposition["report_recommended"] and not disposition.get("compliance_message"):
            raise PolicyViolation("report draft is missing")
        if not disposition["report_recommended"] and disposition.get("compliance_message"):
            raise PolicyViolation("unsolicited compliance draft is forbidden")
        if disposition.get("manual_queue_required") and not disposition.get("compliance_escalation_required_by_policy"):
            # Human queue is separate from compliance escalation; an explicit
            # configured human exception is allowed, but never the fallback.
            if not self.policy.mandatory_human_queue_categories:
                raise PolicyViolation("unsanctioned human queue")
