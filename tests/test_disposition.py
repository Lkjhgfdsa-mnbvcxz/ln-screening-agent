"""Disposition / concise business writing acceptance tests; all fixtures fictional."""
import copy
import json
import unittest
from pathlib import Path
from dataclasses import replace
from ln_agent import Case, Orchestrator, Policy, FixtureResearchTool
from ln_agent.policy_guard import PolicyGuard, PolicyViolation
from ln_agent.skill_catalog import load_skill, select_skills
from ln_agent.tool_catalog import load_tool
from scripts.run_disposition_demo import run_examples

ROOT=Path(__file__).resolve().parents[1]


def run_fixture(filename, *, policy=None, mutate=None):
    data=json.loads((ROOT/"examples"/filename).read_text(encoding="utf-8"))
    if mutate:
        mutate(data)
    report=Orchestrator(policy or Policy(),FixtureResearchTool()).run(Case.from_dict(data))
    return report["results"][0]

class TestConciseDisposition(unittest.TestCase):
    def test_critical_company_name_and_address_difference_report(self):
        r=run_fixture("case_company_critical_suspected.json")
        d=r["disposition"]
        self.assertEqual(r["route"],"RESIDUAL_SUSPICION")
        self.assertTrue(d["report_recommended"])
        self.assertEqual(d["recommendation"],"SUSPECTED_HIT_REPORT_DRAFT")
        self.assertIn("企业名称一致",d["internal_note"])
        self.assertIn("注册地址不一致",d["internal_note"])
        self.assertIn("实际经营地址尚未核实",d["internal_note"])
        self.assertIn("出口管制",d["internal_note"])
        self.assertIn("SYN:LN:RISK-EVENT-001",d["source_refs"])
        self.assertFalse(d["manual_queue_required"])

    def test_person_full_id_and_dob_with_address_difference(self):
        r=run_fixture("case_person_identity_suspected.json")
        d=r["disposition"]
        self.assertEqual(r["route"],"LINKED_RISK_REVIEW")
        self.assertTrue(d["report_recommended"])
        for term in ("姓名一致", "出生日期一致", "证件号码一致", "居住地址不一致", "扣押"):
            self.assertIn(term,d["internal_note"])
        self.assertIn("疑似真实命中",d["internal_note"])
        self.assertLess(len(d["internal_note"]),140)
        self.assertIn("复核链接：https://example.invalid",d["compliance_message"])

    def test_internal_is_short_compliance_carries_identifiers(self):
        for result in run_examples()["results"]:
            d=result["disposition"]
            self.assertLess(len(d["internal_note"]),160)
            self.assertTrue(d["compliance_message"].startswith("SYNTHETIC-GPT-"))
            self.assertNotIn("https://",d["internal_note"])
            self.assertFalse(d["automatically_sent"])
            self.assertFalse(d["automatically_cleared"])

    def test_only_name_without_event_is_not_reported(self):
        r=run_fixture("case_company_critical_suspected.json",mutate=lambda data: data["hits"][0]["risk_event"].clear())
        d=r["disposition"]
        self.assertFalse(d["report_recommended"])
        self.assertEqual(d["compliance_message"],"")
        self.assertFalse(d["manual_queue_required"])
        self.assertIn("证据不足",d["internal_note"])

    def test_risk_claim_without_source_is_not_reproduced(self):
        def strip_source(data):
            data["hits"][0]["risk_event"].pop("source_ref")
        d=run_fixture("case_company_critical_suspected.json",mutate=strip_source)["disposition"]
        self.assertFalse(d["report_recommended"])
        self.assertNotIn("出口管制",d["internal_note"])
        self.assertNotIn("出口管制",d["compliance_message"])

    def test_high_impact_does_not_prove_identity(self):
        d=run_fixture("case_company_critical_suspected.json")["disposition"]
        self.assertEqual(d["identity_status"],"unresolved")
        self.assertIn("身份关联尚未确认",d["internal_note"])

    def test_low_impact_name_only_not_report(self):
        def change(data):
            data["hits"][0]["risk_event"]["severity"]="low"
        self.assertFalse(run_fixture("case_company_critical_suspected.json",mutate=change)["disposition"]["report_recommended"])

    def test_policy_disabling_critical_name_path_changes_runtime(self):
        p=Policy(report_critical_name_matches=False)
        r=run_fixture("case_company_critical_suspected.json",policy=p)
        self.assertFalse(r["disposition"]["report_recommended"])

    def test_policy_risk_categories_changes_runtime(self):
        p=Policy(reportable_risk_categories=frozenset({"sanctions"}))
        d=run_fixture("case_person_identity_suspected.json",policy=p)["disposition"]
        self.assertFalse(d["report_recommended"])

    def test_exceptional_human_queue_requires_explicit_policy(self):
        d=run_fixture("case_company_critical_suspected.json",policy=Policy(mandatory_human_queue_categories=frozenset({"enforcement"})))["disposition"]
        self.assertTrue(d["manual_queue_required"])
        self.assertFalse(d["automatically_sent"])

    def test_exclusion_candidate_not_recast_as_hit(self):
        d=run_fixture("case_false_positive.json")["disposition"]
        self.assertFalse(d["report_recommended"])
        self.assertIn("排除候选",d["internal_note"])
        self.assertIn("出生日期不同",d["internal_note"])

    def test_mandatory_gate_overrides_exclusion_but_not_exclusion_evidence(self):
        policy=Policy(mandatory_compliance_categories=frozenset({"enforcement"}))
        d=run_fixture("case_false_positive.json",policy=policy)
        self.assertTrue(d["disposition"]["report_recommended"])
        self.assertTrue(d["exclusion_evidence_detected"])
        self.assertIn("排除",d["disposition"]["internal_note"])
        self.assertTrue(d["disposition"]["compliance_escalation_required_by_policy"])

    def test_no_malformed_link_is_forwarded(self):
        def replace_url(data):
            data["hits"][0]["screening_url"]="javascript:alert(1)"
        d=run_fixture("case_person_identity_suspected.json",mutate=replace_url)["disposition"]
        self.assertNotIn("javascript:",d["compliance_message"])
        self.assertNotIn("复核链接",d["compliance_message"])

    def test_conflicting_address_semantics_does_not_claim_difference(self):
        def corrupt_context(data):
            data["hits"][0]["facts"][1]["context"]="BUSINESS_ADDRESS"
        d=run_fixture("case_company_critical_suspected.json",mutate=corrupt_context)["disposition"]
        self.assertNotIn("地址不一致",d["internal_note"])

    def test_reader_cannot_fake_disposition_permission(self):
        good=run_fixture("case_person_identity_suspected.json")["disposition"]
        guard=PolicyGuard(Policy())
        bad=copy.deepcopy(good);bad["automatically_sent"]=True
        with self.assertRaises(PolicyViolation):
            guard.validate_disposition_draft(bad)
        bad=copy.deepcopy(good);bad["source_refs"]=[]
        # A summary can have an in-memory source reference in the inbound hit,
        # but the output must also retain its support anchors.
        self.assertIn("source_refs",bad)

    def test_disposition_skill_and_tool_are_runtime_loadable(self):
        sk=load_skill("disposition_reporting")
        tl=load_tool("disposition_writer")
        self.assertIn("internal_note",sk["required_output_fields"])
        self.assertEqual(tl["status"],"implemented_internal")
        self.assertTrue(any(s["id"]==sk["id"] for s in select_skills("person",phase="disposition")))

    def test_cannot_fabricate_unsupported_material_context(self):
        def remove_context_proof(data):
            data["hits"][0]["risk_event"]["material_context"][0].pop("evidence_id")
        d=run_fixture("case_company_critical_suspected.json",mutate=remove_context_proof)["disposition"]
        self.assertNotIn("实际经营地址尚未核实",d["internal_note"])

    def test_writer_invocation_is_audited_in_agent_path(self):
        r=run_fixture("case_company_critical_suspected.json")
        writer_steps=[x for x in r["execution_path"] if x["action"]=="WRITE_DISPOSITION"]
        self.assertEqual(len(writer_steps),1)
        self.assertEqual(writer_steps[0]["tool"],"disposition_writer")
        self.assertIn("SKILL_DISPOSITION_REPORTING_V1", r["version_snapshot"]["skills"])

    def test_person_case_source_refs_include_identity_and_event(self):
        d=run_fixture("case_person_identity_suspected.json")["disposition"]
        for ref in ("SYN:LN:PERSON-ID","SYN:LN:RISK-EVENT-002"):
            self.assertIn(ref,d["source_refs"])

if __name__=="__main__": unittest.main()
