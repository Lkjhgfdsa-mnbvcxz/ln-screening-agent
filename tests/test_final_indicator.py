"""v0.9.6 final triage indicator: business rules, safety fence, roll-up.

The indicator is a DERIVED metric. These tests pin down that it resolves the
business-facing "无结论" bucket without ever rewriting the real disposition.
All fixtures are synthetic.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ln_agent import Case, Orchestrator, Policy, FixtureResearchTool
from ln_agent.evidence import EvidenceResult
from ln_agent.final_indicator import (INDICATOR_LABELS, derive_case_indicator,
                                      derive_final_indicator)
from ln_agent.models import Fact, Hit, Subject
from ln_agent.policy_guard import PolicyGuard, PolicyViolation

ROOT = Path(__file__).resolve().parents[1]


def _fact(side, field, value, eid, origin="ln_structured"):
    return Fact(side=side, field=field, value=value, evidence_id=eid,
                origin=origin, checked=True)


def _subject():
    return Subject(subject_id="SYN-S1", entity_type="person", role="applicant",
                   facts=[_fact("applicant", "name", "Synthetic Person", "a:name", "kyb_verified"),
                          _fact("applicant", "region", "华东", "a:region", "kyb_verified")])


def _hit(event=None):
    return Hit(hit_id="SYN-H1", subject_id="SYN-S1", category="sanctions",
               entity_type="person",
               facts=[_fact("hit", "name", "Synthetic Person", "h:name")],
               risk_event=event or {})


def _derive(*, event=None, hit_facts=None, route="RESIDUAL_SUSPICION",
            recommendation="INSUFFICIENT_EVIDENCE_RECORDED", business=None,
            report=False, gate=None, evidence=None):
    return derive_final_indicator(
        subject=_subject(), hit=_hit(event), evidence=evidence or EvidenceResult(),
        identity="unresolved", route=route, recommendation=recommendation,
        policy=Policy(), gate=gate or {}, business_conclusion=business,
        report_recommended=report, hit_facts=hit_facts or [])


def _run(example, mutate=None):
    data = json.loads((ROOT / "examples" / example).read_text(encoding="utf-8"))
    if mutate:
        mutate(data)
    return Orchestrator(Policy(), FixtureResearchTool()).run(
        Case.from_dict(data))["results"][0]["disposition"]


class FinalIndicatorRules(unittest.TestCase):
    def test_fi1_confirmed_hit_stays_hit(self):
        d = _run("case_true_link.json")
        self.assertEqual(d["business_conclusion"], "命中")
        self.assertEqual(d["final_indicator"], "命中")
        self.assertEqual(d["final_indicator_rule"], "FI-1")
        self.assertTrue(any("硬匹配" in x for x in d["final_indicator_basis"]))

    def test_fi2_existing_report_draft_stays_suspected(self):
        d = _run("case_company_critical_suspected.json")
        self.assertEqual(d["business_conclusion"], "疑似命中")
        self.assertEqual(d["final_indicator"], "疑似命中")

    def test_fi3_missing_only_notice_level_identity_is_false_positive_group(self):
        d = _run("case_company_critical_suspected.json",
                 mutate=lambda data: data["hits"][0]["risk_event"].clear())
        self.assertIsNone(d["business_conclusion"], "indicator must not rewrite the draft")
        self.assertEqual(d["business_conclusion_status"], "NO_CONCLUSION")
        self.assertEqual(d["final_indicator"], "误报·未命中")
        self.assertEqual(d["final_indicator_rule"], "FI-3")
        self.assertTrue(d["final_indicator_does_not_clear_hit"])
        self.assertFalse(d["automatically_cleared"])
        self.assertFalse(d["final_indicator_changes_business_conclusion"])

    def test_fi2_serious_event_with_consistent_incident_location(self):
        event = {"source_ref": "synthetic://bulletin/1", "summary": "合成重大事由",
                 "severity": "critical", "event_region": "华东"}
        d = _derive(event=event)
        self.assertEqual(d["final_indicator"], "疑似命中")
        self.assertTrue(d["final_indicator_inputs"]["serious"])
        self.assertTrue(d["final_indicator_inputs"]["location_consistent"])
        self.assertFalse(d["final_indicator_inputs"]["identity_fields_available"])
        self.assertTrue(any("事发地" in x for x in d["final_indicator_basis"]))

    def test_fi3_same_missing_identity_but_location_unknown(self):
        event = {"source_ref": "synthetic://bulletin/1", "summary": "合成重大事由",
                 "severity": "critical", "event_region": "境外某地"}
        d = _derive(event=event)
        self.assertTrue(d["final_indicator_inputs"]["serious"])
        self.assertFalse(d["final_indicator_inputs"]["location_consistent"])
        self.assertEqual(d["final_indicator"], "误报·未命中")

    def test_fi2_policy_block_and_source_conflict_are_never_cleared(self):
        for route, rec in (("POLICY_BLOCKED_REVIEW", "TECHNICAL_OR_POLICY_HOLD"),
                           ("EVIDENCE_CONFLICT_REVIEW", "UNRESOLVED_EVIDENCE_CHECK")):
            with self.subTest(route=route):
                d = _derive(route=route, recommendation=rec)
                self.assertEqual(d["final_indicator"], "疑似命中")
                self.assertTrue(any("不得归入误报" in x for x in d["final_indicator_basis"]))

    def test_fi2_mandatory_escalation_is_retained(self):
        d = _derive(gate={"compliance_escalation_required": True})
        self.assertEqual(d["final_indicator"], "疑似命中")

    def test_metric_is_deterministic_and_has_only_three_labels(self):
        first = _derive()
        second = _derive()
        self.assertEqual(first, second)
        self.assertIn(first["final_indicator"], INDICATOR_LABELS)

    def test_guard_rejects_tampered_indicator(self):
        d = _run("case_true_link.json")
        guard = PolicyGuard(Policy())
        for key, bad in (("final_indicator", "放行"),
                         ("final_indicator_rule", "FI-99"),
                         ("final_indicator_status", "APPROVED"),
                         ("final_indicator_does_not_clear_hit", False),
                         ("final_indicator_changes_business_conclusion", True),
                         ("final_indicator_basis", [])):
            with self.subTest(key=key):
                copy = dict(d)
                copy[key] = bad
                with self.assertRaises(PolicyViolation):
                    guard.validate_disposition_draft(copy)

    def test_guard_rejects_false_positive_downgrade(self):
        d = _run("case_company_critical_suspected.json")
        d["final_indicator"] = "误报·未命中"
        with self.assertRaises(PolicyViolation):
            PolicyGuard(Policy()).validate_disposition_draft(d)

    def test_contract_declares_the_derived_metric_boundary(self):
        contract = json.loads((ROOT / "skills" / "disposition_reporting" /
                               "contract.json").read_text(encoding="utf-8"))
        metric = contract["derived_metric"]
        self.assertEqual(metric["kind"], "TRIAGE_METRIC")
        self.assertEqual(metric["allowed_labels"], list(INDICATOR_LABELS))
        self.assertIn("business_conclusion", metric["must_not_change"])
        self.assertIn("因信息不足创建人工调查任务", metric["prohibited_actions"])
        for field in ("final_indicator", "final_indicator_basis",
                      "final_indicator_does_not_clear_hit"):
            self.assertIn(field, contract["required_output_fields"])


class CaseRollup(unittest.TestCase):
    def test_rollup_uses_highest_present_label(self):
        r = derive_case_indicator(["误报·未命中"] * 8 + ["疑似命中", "疑似命中"])
        self.assertEqual(r["case_final_indicator"], "疑似命中")
        self.assertEqual(r["final_indicator_distribution"],
                         {"命中": 0, "疑似命中": 2, "误报·未命中": 8})
        self.assertEqual(r["escalation_hits"], 2)
        self.assertAlmostEqual(r["escalation_rate"], 0.2)

    def test_rollup_confirmed_hit_dominates(self):
        r = derive_case_indicator(["命中"] + ["误报·未命中"] * 9)
        self.assertEqual(r["case_final_indicator"], "命中")
        self.assertAlmostEqual(r["escalation_rate"], 0.1)

    def test_empty_rollup_is_safe(self):
        r = derive_case_indicator([])
        self.assertEqual(r["case_final_indicator"], "误报·未命中")
        self.assertEqual(r["escalation_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
