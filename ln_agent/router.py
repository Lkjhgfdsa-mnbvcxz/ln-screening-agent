"""Per-hit dynamic routing. Q0 Gate first, then evidence, then bounded research/RSA."""
from __future__ import annotations
from dataclasses import asdict
from time import perf_counter
from typing import Callable
from .models import Case, Hit, Fact, Decision
from .policy import Policy
from .policy_guard import PolicyGuard, PolicyViolation
from .evidence import evaluate
from .tools import InvestigationAgent
from .suspicion import SuspicionAgent
from .skills import get_skill, ordered_queries
from .skill_catalog import select_skills
from .fact_verification import FactVerifier
from .corroboration import assess_corroboration
from .risk_gate import RiskGate
from .rules.registry import RuleRegistry
from .explain import build_explanation, validate_explanation
from .disposition import build_disposition

class DecisionRouter:
    def __init__(self,policy:Policy,investigator:InvestigationAgent, verifier:FactVerifier|None=None):
        self.policy=policy
        self.investigator=investigator
        self.suspicion_agent=SuspicionAgent(policy)
        self.guard=PolicyGuard(policy)
        self.risk_gate=RiskGate(policy)
        self.registry=RuleRegistry(policy)
        self.verifier=verifier or FactVerifier()

    def run_hit(self,case:Case,hit:Hit, *, on_event: Callable[[dict], None] | None = None)->Decision:
        hit_started = perf_counter()
        def emit(kind: str, stage: str, *, status: str = "ok", duration_ms: float | None = None, **details):
            if on_event is None:
                return
            item = {"kind":kind,"stage":stage,"case_id":case.case_id,
                    "hit_id":hit.hit_id,"status":status,"details":details}
            if duration_ms is not None:
                item["duration_ms"] = round(duration_ms, 3)
            # Observability is advisory: a dashboard failure must not influence screening.
            try:
                on_event(item)
            except Exception:
                pass
        emit("HIT_STARTED", "orchestrator", entity_type=hit.entity_type,
             category=hit.category, research_actions=len(hit.research_keys))
        subject=next(x for x in case.subjects if x.subject_id==hit.subject_id)
        skill=get_skill(subject.entity_type)
        active_skills=select_skills(subject.entity_type, hit.research_keys)
        emit("SKILL_SELECTED", "skill", skill_ids=[x["id"] for x in active_skills],
             contract_applied=True)
        facts=list(hit.facts)
        _t=perf_counter()
        check=self.guard.check_ingest(case,hit,facts)
        emit("POLICY_CHECK", "policy", check="ingest", allowed=check.allowed,
             duration_ms=(perf_counter()-_t)*1000)
        if not check.allowed:
            raise PolicyViolation("data ingest rejected: "+check.reason)
        history=[];done_keys=set();actions=[];tried_actions=[];evidence_of_attempt=[]
        doc_evidence=[];hit_evidence_links=[];verification_records=[];valid_verification_ids=set()
        # Q0: gate flags are computed BEFORE evaluating exclusion candidates and
        # are immutable for this run, regardless of which branch eventually returns.
        _t=perf_counter()
        gate=self.guard.assess_risk_gate(hit)
        emit("GATE_CHECK", "risk_gate", flags=list(gate.flags),
             duration_ms=(perf_counter()-_t)*1000)
        gate_flags=list(gate.flags)
        gate_history=[]
        execution_path=[]
        while True:
            corroboration = assess_corroboration(
                case_id=case.case_id, hit_id=hit.hit_id,
                records=verification_records,
                minimum_independent_sources=self.policy.minimum_independent_sources)
            # A cross-source claim is only eligible after reviewed independent
            # agreement if the optional policy demands corroboration.
            effective_ids = set(valid_verification_ids)
            if self.policy.require_independent_corroboration_for_document_facts:
                effective_ids = {vid for report in corroboration
                                 if report.status == "CORROBORATED"
                                 for vid in report.verification_ids}
            _t=perf_counter()
            result=evaluate(subject.facts,facts,hit.entity_type, frozenset(effective_ids))
            emit("RULE_EVALUATED", "rule_engine", round=len(history)+1,
                 exclusion_rules=list(result.exclusion_rules), linked_rules=list(result.linked_rules),
                 soft_signals=list(result.soft_signals), issue_count=len(result.data_issues),
                 duration_ms=(perf_counter()-_t)*1000)
            # Active WorkBuddy P01-P10 registry: filter disabled rule candidates in runtime.
            result,rule_findings=self.registry.filter_and_find(result)
            emit("RULE_REGISTRY_CHECK", "policy", rule_ids=[f["rule_id"] for f in rule_findings])
            # Gate Q0 before any early conclusion; never overwritten by EBE/RSA.
            current_state=("conflict" if result.data_issues else
                           "excluded_candidate" if result.exclusion_rules else
                           "strong_link" if result.linked_rules else "unresolved")
            gate_decision=self.risk_gate.evaluate(hit,current_state,gate_history)
            emit("GATE_CHECK", "risk_gate", flags=list(gate_decision.conditions),
                 escalation_required=gate_decision.compliance_escalation_required)
            gate_history=list(gate_decision.trigger_history)
            execution_path.append({"action":"EVALUATE", "round":len(history)+1,
                                   "risk_gate":list(gate_decision.conditions),
                                   "rules":[f["rule_id"] for f in rule_findings]})
            history.append({
              "step":len(history)+1,"known_hit_facts":len(facts),
              "checked_research_keys":sorted(done_keys),"applied_skill":skill["id"],
              "skill_bundle":[s["id"] for s in active_skills],
              "exclusion_rules":result.exclusion_rules[:],"linked_rules":result.linked_rules[:],
              "data_issues":result.data_issues[:],"gate_flags":gate_flags[:]
            })
            evidence=asdict(result)
            def finish(route:str,identity:str,reasons:list[str],suspicion=None,
                       *, investigation_status:str="not_exhausted",skip_reason:str|None=None):
                # Final independent Gate check: conclusions cannot silently drop risk flags.
                final_gate=self.risk_gate.evaluate(hit,identity,gate_history)
                final_gate_dict=final_gate.to_dict()
                flags=list(dict.fromkeys(gate_flags+list(final_gate.conditions)))
                explanation=build_explanation(route=route,reasons=reasons,evidence=evidence,
                      gate=final_gate_dict,actions=actions,skip_reason=skip_reason,
                      suspicion=suspicion,investigation_status=investigation_status)
                if not validate_explanation(explanation):
                    raise RuntimeError("five-WHY explanation incomplete")
                stop_map={"EXCLUSION_CANDIDATE":"SUFFICIENT_EXCLUSION_EVIDENCE",
                          "LINKED_RISK_REVIEW":"SUFFICIENT_LINK_EVIDENCE",
                          "EVIDENCE_CONFLICT_REVIEW":"EVIDENCE_CONFLICT",
                          "FACT_VERIFICATION_REVIEW":"AWAITING_FACT_VERIFICATION",
                          "RESIDUAL_SUSPICION":"NO_ACTIONABLE_IDENTITY_LEAD",
                          "TOOL_FAILURE_REVIEW":"RESOURCE_OR_TOOL_FAILURE",
                          "POLICY_BLOCKED_REVIEW":"POLICY_BLOCKED"}
                stop_reason=stop_map.get(route,"REVIEW_REQUIRED")
                self.guard.check_state_transition("AUTO_CONCLUSION")
                _t=perf_counter()
                disposition=build_disposition(case=case,subject=subject,hit=hit,
                    evidence=result,route=route,identity=identity,
                    suspicion=suspicion,policy=self.policy,gate=final_gate_dict,
                    evidence_refs=list(result.anchors))
                self.guard.validate_disposition_draft(disposition)
                emit("POLICY_CHECK", "policy", check="disposition", allowed=True)
                # A first-class deterministic internal Tool backed by an
                # executable Skill contract (not an undeclared prompt step).
                disposition_skill=select_skills(subject.entity_type,hit.research_keys,
                                                 phase="disposition")[-1]
                execution_path.append({"action":"WRITE_DISPOSITION",
                                       "tool":"disposition_writer",
                                       "skill":disposition_skill["id"],
                                       "report_recommended":disposition["report_recommended"]})
                emit("SKILL_SELECTED", "skill", skill_ids=[disposition_skill["id"]], contract_applied=True)
                emit("TOOL_FINISHED", "disposition", tool="disposition_writer", action="write_draft",
                     duration_ms=(perf_counter()-_t)*1000,
                     report_recommended=disposition["report_recommended"])
                emit("HIT_FINISHED", "orchestrator", route=route, identity=identity,
                     recommendation=disposition.get("recommendation"),
                     duration_ms=(perf_counter()-hit_started)*1000)
                return Decision(
                    hit_id=hit.hit_id,route=route,identity=identity,suspicion=suspicion,
                    evidence=evidence,reasons=reasons,actions=list(actions),history=history,
                    review_required=True,policy_version=self.policy.version,
                    disposition_flags=flags,
                    exclusion_evidence_detected=bool(result.exclusion_rules),
                    exclusion_authorized=self.guard.authorized_exclusion(result.exclusion_rules),
                    investigation_status=investigation_status,skip_reason=skip_reason,
                    tried_actions=list(tried_actions),evidence_of_attempt=list(evidence_of_attempt),
                    document_evidence=list(doc_evidence),
                    hit_evidence_links=list(hit_evidence_links),
                    verification_records=list(verification_records),
                    corroboration=[x.to_dict() for x in corroboration],
                    rule_findings=rule_findings,
                    gate=final_gate_dict,
                    gate_final_check={"alert_preserved_after_conclusion":
                        final_gate.screening_alert_observed,
                        "compliance_escalation_retained": final_gate.compliance_escalation_required},
                    explanation=explanation,
                    execution_path=list(execution_path),
                    stop_reason=stop_reason,
                    disposition=disposition,
                    version_snapshot={"policy":self.policy.version,
                      "rules":"INTEGRATED-P01-P10", "registry":str(self.registry.coverage()["enabled"]),
                      "skills":"+".join(list(dict.fromkeys(
                        [s["id"] for s in active_skills]+[disposition_skill["id"]])))}
                )
            try:
                self.guard.validate_hard_rules(result.exclusion_rules,skill)
            except PolicyViolation as exc:
                return finish("POLICY_BLOCKED_REVIEW","unresolved",[str(exc)],
                              investigation_status="blocked")
            if any(x.status == "CONTRADICTORY_SOURCES" for x in corroboration):
                return finish("EVIDENCE_CONFLICT_REVIEW", "conflict",
                              ["同一经核验事件存在跨来源事实冲突，必须进一步核实"],
                              investigation_status="needs_verification")
            if result.data_issues or (result.exclusion_rules and result.linked_rules):
                return finish("EVIDENCE_CONFLICT_REVIEW","conflict",
                              ["数据内部矛盾或证件历史待核实，禁止直接排除/确认"],
                              investigation_status="needs_verification")
            if result.exclusion_rules:
                return finish("EXCLUSION_CANDIDATE","excluded_candidate",result.exclusion_rules,
                              investigation_status="completed_after_hard_evidence")
            if result.linked_rules and any(x in result.linked_rules for x in
                         ("DOCUMENT_EXACT_MATCH","COMPANY_REGISTRATION_MATCH")):
                return finish("LINKED_RISK_REVIEW","strong_link",result.linked_rules,
                              investigation_status="completed_after_hard_evidence")
            remaining=ordered_queries(skill,[x for x in hit.research_keys if x not in done_keys])
            if remaining and len(done_keys)<self.policy.max_research_actions_per_hit:
                key=remaining[0]
                tool_name="document_intelligence" if key.startswith("doc:") else "fixture_research"
                _t=perf_counter()
                gate_check=self.guard.check_tool_call(tool_name,key,skill,len(done_keys))
                emit("TOOL_AUTHORIZED", "policy", tool=tool_name, action_key=key,
                     allowed=gate_check.allowed, duration_ms=(perf_counter()-_t)*1000)
                try:
                    if not gate_check.allowed:
                        raise PolicyViolation(gate_check.reason)
                except PolicyViolation as exc:
                    return finish("POLICY_BLOCKED_REVIEW","unresolved",[str(exc)],
                                  investigation_status="blocked")
                done_keys.add(key) # before query: prevents duplicate roundtrips
                emit("TOOL_STARTED", "investigation", tool=tool_name, action_key=key,
                     skill_id=skill["id"])
                _tool_started=perf_counter()
                execution_path.append({"action":"INVESTIGATE","key":key,"tool":tool_name})
                actions.append(f"RESEARCH_QUERY:{key}")
                tried_actions.append({"action":key,"outcome":"attempted"})
                try:
                    subject_queries=[f.value for f in subject.facts if f.field in
                                     ("name","company_name","registration_number","document_number")]
                    hit_queries=[f.value for f in facts if f.field in
                                 ("name","company_name","registration_number")]
                    outcome=self.investigator.investigate_with_evidence(key,subject_queries+hit_queries)
                    new_facts=self.guard.validate_facts(outcome.facts,skill)
                    emit("TOOL_FINISHED", "investigation", tool=tool_name, action_key=key,
                         fact_count=len(new_facts), document_count=len(outcome.document_packets),
                         duration_ms=(perf_counter()-_tool_started)*1000)
                except PolicyViolation as exc:
                    tried_actions[-1]["outcome"]="policy_rejected"
                    emit("TOOL_FINISHED", "investigation", status="blocked",tool=tool_name,
                         duration_ms=(perf_counter()-_tool_started)*1000)
                    evidence_of_attempt.append({"action":key,"error":str(exc)})
                    return finish("POLICY_BLOCKED_REVIEW","unresolved",[str(exc)],
                                  investigation_status="blocked")
                except Exception as exc:
                    tried_actions[-1]["outcome"]="error"
                    emit("TOOL_FINISHED", "investigation", status="error",tool=tool_name,
                         error_type=type(exc).__name__, duration_ms=(perf_counter()-_tool_started)*1000)
                    history[-1]["research_error"]=type(exc).__name__
                    evidence_of_attempt.append({"action":key,"error_type":type(exc).__name__})
                    return finish("TOOL_FAILURE_REVIEW","unresolved",
                                  ["调查工具不可用，不等于没有关联或低风险"],
                                  investigation_status="tool_failed")
                before={(f.evidence_id,f.field,f.value) for f in facts}
                accepted=[f for f in new_facts if (f.evidence_id,f.field,f.value) not in before]
                facts.extend(accepted)
                emit("FACTS_RECEIVED", "evidence", candidates=len(accepted),
                     evidence_ids=[f.evidence_id for f in accepted][:12])
                tried_actions[-1]["outcome"]="completed"
                tried_actions[-1]["new_fact_candidates"]=len(accepted)
                for packet in outcome.document_packets:
                    doc_evidence.append(packet)
                    parsed_doc=(self.investigator.tool.get_parsed_document(packet["document_id"])
                                if hasattr(self.investigator.tool,"get_parsed_document") else None)
                    verified=self.verifier.verify_packet(case_id=case.case_id,hit_id=hit.hit_id,
                                   document=parsed_doc,packet=packet)
                    ids={r["verification_id"] for r in verified.verification_records
                         if r["status"]=="VERIFIED_FOR_COMPARISON"}
                    self.guard.validate_reviewed_document_facts(verified.verified_facts,ids)
                    valid_verification_ids.update(ids)
                    verification_records.extend(verified.verification_records)
                    emit("FACT_VERIFICATION", "evidence", document_id=packet["document_id"],
                         reviewed=len(verified.verification_records), accepted=len(verified.verified_facts))
                    facts.extend(verified.verified_facts)
                    for span in packet["evidence_spans"]:
                        hit_evidence_links.append({
                          "case_id":case.case_id,"hit_id":hit.hit_id,
                          "evidence_id":span["evidence_id"],
                          "document_id":packet["document_id"],
                          "source_hash":packet["sha256"],
                          "direction":"IDENTITY_FACT_VERIFIED" if any(
                            r["evidence_id"]==span["evidence_id"] and r["status"]=="VERIFIED_FOR_COMPARISON"
                            for r in verified.verification_records) else "UNDETERMINED",
                          "applicability_checked":any(
                            r["evidence_id"]==span["evidence_id"] and r["status"]=="VERIFIED_FOR_COMPARISON"
                            for r in verified.verification_records),
                          "reason":"核实记录已绑定到本命中" if any(
                            r["evidence_id"]==span["evidence_id"] and r["status"]=="VERIFIED_FOR_COMPARISON"
                            for r in verified.verification_records) else "已定位原文，尚未核实资料及人物对应关系"
                        })
                    evidence_of_attempt.append({
                        "action":key,"document_id":packet["document_id"],
                        "source_url":packet["source_url"],"sha256":packet["sha256"],
                        "target_matches":packet["coverage"]["target_matches"],
                        "material_leads":packet["coverage"]["material_leads"]
                    })
                if not outcome.document_packets:
                    evidence_of_attempt.append({"action":key,"received_fact_count":len(accepted)})
                continue
            # A plausible, high-impact document fact awaiting provenance/attribution
            # verification is NOT equivalent to exhausted identity research.
            outstanding=[r for r in verification_records if r["status"]!="VERIFIED_FOR_COMPARISON"]
            if (self.policy.require_independent_corroboration_for_document_facts and
                any(r["status"] == "VERIFIED_FOR_COMPARISON" and
                    r.get("verification_id") not in effective_ids for r in verification_records)):
                return finish("FACT_CORROBORATION_REVIEW", "unresolved",
                              ["人工已核验单源事实，但独立原始来源尚未达到当前策略门槛；不能据此硬排除"],
                              investigation_status="awaiting_corroboration")
            if outstanding:
                return finish("FACT_VERIFICATION_REVIEW","unresolved",
                    ["文档包含尚未核实的人物事件事实，必须先确认来源、上下文与对应主体；不得进入低分放行"],
                    investigation_status="awaiting_verification",skip_reason=None)
            if "DOB_EXACT_MATCH" in result.linked_rules and "name_exact" in result.soft_signals:
                return finish("LINKED_RISK_REVIEW","strong_link",
                    ["DOB_EXACT_MATCH","NAME_EXACT_MATCH","强关联仍需人工核实"],
                    investigation_status="completed_after_hard_evidence")
            skip_reason=("NO_RESEARCH_KEYS" if not hit.research_keys else
                         "RESEARCH_ACTIONS_COMPLETED_OR_BUDGET_REACHED")
            active_skills=select_skills(subject.entity_type, hit.research_keys, phase="suspicion")
            emit("SKILL_SELECTED", "skill", skill_ids=[x["id"] for x in active_skills],
                 contract_applied=True)
            execution_path.append({"action":"RESIDUAL_SUSPICION",
                                   "skill_bundle":[s["id"] for s in active_skills]})
            _t=perf_counter()
            suspicion=self.suspicion_agent.assess(hit,result)
            emit("SUSPICION_EVALUATED", "suspicion", score_available=suspicion.get("score") is not None,
                 duration_ms=(perf_counter()-_t)*1000)
            return finish("RESIDUAL_SUSPICION","unresolved",
                 ["无可靠排除或强关联依据，当前无可执行的进一步查询；非自动放行"],suspicion,
                 investigation_status="exhausted",skip_reason=skip_reason)
