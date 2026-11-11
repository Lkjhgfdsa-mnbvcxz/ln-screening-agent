"""Regressions for defects found while running 8 authorized real BOSS checklists.

The public fixtures here are synthetic; they reproduce the DATA SHAPE that
exposed each defect without containing any real merchant information.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ln_agent import Case, FixtureResearchTool, Orchestrator, Policy
from ln_agent.policy_guard import PolicyGuard
from ln_agent.risk_categories import any_category, risk_categories
from ln_agent.risk_gate import RiskGate
from ln_agent.models import Hit, Subject, Fact
from ln_agent.workbuddy_adapters import (CaptureBundle, authorized_policy,
                                         build_capture_tools)

ROOT = Path(__file__).resolve().parents[1]


class Defect1ChineseCategoryLabels(unittest.TestCase):
    """Real BOSS rows say 制裁/执法/PEP/不利媒体, not the English aliases."""

    def test_chinese_labels_normalize_to_canonical_categories(self):
        self.assertEqual(risk_categories("制裁,执法"), ("sanctions", "enforcement"))
        self.assertEqual(risk_categories("不利媒体"), ("adverse_media",))
        self.assertEqual(risk_categories("PEP"), ("pep",))
        self.assertTrue(any_category("制裁", frozenset({"sanctions"})))
        self.assertTrue(any_category("执法", frozenset({"enforcement"})))

    def test_sanctions_hit_keeps_mandatory_screening_review_flag(self):
        hit = Hit.from_dict({"hit_id": "SYN-H", "subject_id": "SYN-S",
                             "category": "制裁,执法", "entity_type": "person"})
        gate = RiskGate(Policy()).evaluate(hit, "unresolved")
        self.assertIn("SCREENING_REVIEW_REQUIRED", gate.conditions)
        self.assertTrue(gate.requires_manual_screening_review)
        flags = PolicyGuard(Policy()).assess_risk_gate(hit).flags
        self.assertIn("SCREENING_REVIEW_REQUIRED", flags)

    def test_reportable_category_check_sees_chinese_label(self):
        hit = Hit.from_dict({"hit_id": "SYN-H", "subject_id": "SYN-S",
                             "category": "执法", "entity_type": "person"})
        self.assertTrue(any_category(hit.category, Policy().reportable_risk_categories))


class Defect2ResearchEvidenceAndNote(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = json.loads((ROOT / "examples" / "case_workbuddy_capture.json").read_text(encoding="utf-8"))
        bundle = CaptureBundle.from_json(ROOT / "examples" / "workbuddy_capture_bundle.json")
        report = Orchestrator(authorized_policy(), FixtureResearchTool({}),
                              extra_tools=build_capture_tools(bundle)).run(Case.from_dict(raw))
        cls.by_id = {r["hit_id"]: r for r in report["results"]}

    def test_internal_note_includes_dob_conflict_discovered_by_research(self):
        # Before the fix the note said only "姓名一致；排除依据待确认。" even
        # though a complete, conflicting DOB was acquired during investigation.
        note = self.by_id["H1"]["disposition"]["internal_note"]
        self.assertIn("出生日期不同", note)
        self.assertIn("1979-11-03", note)

    def test_research_facts_are_exported_with_full_provenance(self):
        facts = self.by_id["H1"]["research_facts"]
        self.assertEqual(len(facts), 1)
        row = facts[0]
        self.assertEqual(row["source_tool"], "workbuddy_browser_readonly")
        self.assertEqual(row["field"], "dob")
        self.assertEqual(row["origin"], "ln_structured")
        self.assertTrue(row["checked"])
        self.assertEqual(row["evidence_id"], "SYN-WB-CAPTURE-001:H1:ln:dob")
        self.assertIn("action_key", row)

    def test_model_facts_are_recorded_as_unchecked(self):
        model = [f for f in self.by_id["H2"]["research_facts"]
                 if f["source_tool"] == "workbuddy_llm_capture"]
        self.assertTrue(model)
        self.assertTrue(all(f["origin"] == "model_extracted" and f["checked"] is False
                            for f in model))
        self.assertEqual(self.by_id["H2"]["disposition"]["business_conclusion"], None)


class Defect3DesignedDisagreementWithHumanReview(unittest.TestCase):
    """Region/province difference must NOT be auto-converted into 未命中.

    Two real checklists were closed by humans as 误报 with reasons
    'different province' / '无法确认为同一企业'. The Skill contract lists
    '跨省居住即排除' as a prohibited shortcut; matching the human conclusion
    by lowering the evidence threshold would be a policy violation.
    """

    def test_region_only_difference_never_creates_exclusion_candidate(self):
        case = Case.from_dict({
            "case_id": "SYN-REGION-ONLY",
            "subjects": [{"subject_id": "S", "entity_type": "person", "role": "applicant",
                          "facts": [
                              {"side": "applicant", "field": "name", "value": "Syn, Theta",
                               "evidence_id": "SYN-REGION-ONLY:app:name",
                               "origin": "kyb_verified", "checked": True},
                              {"side": "applicant", "field": "region", "value": "Sichuan",
                               "evidence_id": "SYN-REGION-ONLY:app:region",
                               "origin": "kyb_verified", "checked": True}]}],
            "hits": [{"hit_id": "H", "subject_id": "S", "category": "执法",
                      "entity_type": "person",
                      "facts": [
                          {"side": "hit", "field": "name", "value": "Syn, Theta",
                           "evidence_id": "SYN-REGION-ONLY:H:name",
                           "origin": "ln_structured", "checked": True},
                          {"side": "hit", "field": "region", "value": "Hainan",
                           "evidence_id": "SYN-REGION-ONLY:H:region",
                           "origin": "ln_structured", "checked": True}]}]})
        r = Orchestrator(Policy(), FixtureResearchTool({})).run(case)["results"][0]
        self.assertNotIn("DOB_EXACT_CONFLICT", r["evidence"]["exclusion_rules"])
        self.assertIsNone(r["disposition"]["business_conclusion"])
        self.assertFalse(r["disposition"]["manual_queue_required"])
        self.assertFalse(r["disposition"]["automatically_cleared"])

    def test_insufficient_evidence_does_not_open_a_human_queue_with_chinese_category(self):
        case = Case.from_dict({
            "case_id": "SYN-NO-QUEUE",
            "subjects": [{"subject_id": "S", "entity_type": "person", "role": "applicant",
                          "facts": [{"side": "applicant", "field": "name", "value": "Syn, Theta",
                                     "evidence_id": "SYN-NO-QUEUE:app:name",
                                     "origin": "kyb_verified", "checked": True}]}],
            "hits": [{"hit_id": "H", "subject_id": "S", "category": "制裁",
                      "entity_type": "person",
                      "facts": [{"side": "hit", "field": "name", "value": "Syn, Theta",
                                 "evidence_id": "SYN-NO-QUEUE:H:name",
                                 "origin": "ln_structured", "checked": True}]}]})
        r = Orchestrator(Policy(), FixtureResearchTool({})).run(case)["results"][0]
        self.assertIn("SCREENING_REVIEW_REQUIRED", r["gate"]["conditions"])
        self.assertFalse(r["disposition"]["manual_queue_required"])
        self.assertFalse(r["disposition"]["automatically_sent"])
        self.assertIsNone(r["disposition"]["business_conclusion"])


if __name__ == "__main__":
    unittest.main()
