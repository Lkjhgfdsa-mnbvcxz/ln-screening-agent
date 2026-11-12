"""v0.9.7: plain-language, DISPLAY-ONLY explanation of an existing decision.

Reviewers could not read the output: it showed status codes and rule ids but
never answered "how exactly did this hit?" or "how were the others excluded?".
These tests pin down that the explanation is human-readable, self-consistent
with its own comparison table, and fenced so it can never become a decision.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ln_agent import Case, Orchestrator, Policy, FixtureResearchTool
from ln_agent.policy_guard import PolicyGuard, PolicyViolation
from ln_agent.skill_catalog import load_skill

ROOT = Path(__file__).resolve().parents[1]

CASE_HIT = "case_true_link.json"
CASE_PERSON = "case_person_identity_suspected.json"
CASE_FALSE_POSITIVE = "case_false_positive.json"
CASE_SUSPECTED = "case_company_critical_suspected.json"


def _run(example: str):
    data = json.loads((ROOT / "examples" / example).read_text(encoding="utf-8"))
    return Orchestrator(Policy(), FixtureResearchTool()).run(Case.from_dict(data))


def _plain(example: str) -> dict:
    return _run(example)["results"][0]["disposition"]["plain_summary"]


class PlainLanguageShapeTests(unittest.TestCase):
    def test_every_decision_carries_a_display_only_summary(self):
        for example in (CASE_HIT, CASE_PERSON, CASE_FALSE_POSITIVE, CASE_SUSPECTED):
            with self.subTest(example=example):
                report = _run(example)
                for result in report["results"]:
                    p = result["disposition"]["plain_summary"]
                    self.assertEqual(p["kind"], "DISPLAY_ONLY")
                    self.assertIs(p["changes_business_conclusion"], False)
                    self.assertIs(p["adds_evidence"], False)
                    self.assertIs(p["clears_hit"], False)
                    for key in ("headline", "why", "why_not", "next_step",
                                "evidence", "caveat"):
                        self.assertTrue(p[key], f"missing {key}")
                    self.assertTrue(p["compare"])
                    for row in p["compare"]:
                        self.assertEqual(set(row), {"field", "subject", "list",
                                                    "result", "note"})
                        self.assertIn(row["result"],
                                      ("一致", "明确冲突", "无法比对", "脱敏"))

    def test_summary_is_deterministic_across_runs(self):
        self.assertEqual(_plain(CASE_HIT), _plain(CASE_HIT))

    def test_confirmed_hit_explains_what_made_it_a_hit(self):
        p = _plain(CASE_HIT)
        self.assertIn("完全一致", p["headline"] + p["why"])
        self.assertIn("唯一标识", p["why"])
        self.assertIn("没有判为", p["why_not"])
        self.assertNotIn("放行", p["headline"])
        hard = [r for r in p["compare"] if r["result"] == "一致"]
        self.assertTrue(hard, "confirmed hit must show the matched identity field")

    def test_excluded_hit_explains_how_it_was_excluded_and_is_not_a_clearance(self):
        p = _plain(CASE_FALSE_POSITIVE)
        text = p["why"] + p["why_not"]
        self.assertIn("同名不同主体", text)
        self.assertIn("明确冲突", text)
        self.assertIn("不是「放行」", p["why_not"])
        self.assertIn("不改写", p["why_not"])  # FI axis explained, not hidden
        self.assertTrue(any(r["result"] == "明确冲突" for r in p["compare"]))

    def test_soft_address_conflict_is_not_called_a_hard_exclusion(self):
        """An address can change; only document/DOB/registration identify a
        subject. Saying 'no conflicts' while showing a red conflict row was the
        exact machine-speak that triggered this change."""
        p = _plain(CASE_PERSON)
        self.assertTrue(any(r["field"] == "地址" and r["result"] == "明确冲突"
                            for r in p["compare"]))
        self.assertIn("不构成排除依据", p["why_not"])
        self.assertNotIn("没有任何硬身份字段冲突", p["why_not"])

    def test_unresolved_hit_never_sounds_like_a_whitelist(self):
        p = _plain("case_workbuddy_capture.json")
        self.assertIn("不是「放行」", p["why_not"])
        self.assertIn("不是「白名单」", p["why_not"])
        # No raw field ids in a reviewer-facing sentence.
        self.assertNotIn("dob", p["why"] + p["why_not"] + p["headline"])
        # Enterprise case must not duplicate the identifier label.
        company = _run("case_workbuddy_capture.json")["results"][-1]["disposition"]["plain_summary"]
        self.assertNotIn("企业注册号、企业注册号", company["why"])

    def test_suspected_hit_does_not_claim_clearance_from_info_gaps(self):
        p = _plain(CASE_SUSPECTED)
        self.assertIn("不能", p["why_not"])
        self.assertIn("不得放行", p["next_step"])
        self.assertNotIn("已放行", p["headline"] + p["why"] + p["why_not"])


class DisplayLayerGuardTests(unittest.TestCase):
    def setUp(self):
        self.good = _run(CASE_HIT)["results"][0]["disposition"]
        self.guard = PolicyGuard(Policy())

    def test_contract_declares_a_display_only_layer(self):
        skill = load_skill("disposition_reporting")
        self.assertEqual(skill["version"], "1.2")
        layer = skill["display_layer"]
        self.assertEqual(layer["name"], "plain_summary")
        self.assertEqual(layer["kind"], "DISPLAY_ONLY")
        self.assertIn("plain_summary", skill["required_output_fields"])

    def test_guard_accepts_the_generated_disposition(self):
        self.guard.validate_disposition_draft(copy.deepcopy(self.good))

    def test_guard_requires_the_plain_summary(self):
        bad = copy.deepcopy(self.good)
        del bad["plain_summary"]
        with self.assertRaises(PolicyViolation):
            self.guard.validate_disposition_draft(bad)

    def test_guard_rejects_summary_that_claims_to_decide(self):
        for key in ("changes_business_conclusion", "adds_evidence", "clears_hit"):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.good)
                bad["plain_summary"][key] = True
                with self.assertRaises(PolicyViolation):
                    self.guard.validate_disposition_draft(bad)

    def test_guard_rejects_missing_field_comparison(self):
        bad = copy.deepcopy(self.good)
        bad["plain_summary"]["compare"] = []
        with self.assertRaises(PolicyViolation):
            self.guard.validate_disposition_draft(bad)

    def test_guard_rejects_unresolved_hit_described_as_clearance(self):
        unresolved = _run("case_workbuddy_capture.json")["results"][0]["disposition"]
        self.guard.validate_disposition_draft(copy.deepcopy(unresolved))
        bad = copy.deepcopy(unresolved)
        bad["plain_summary"]["why_not"] = "本条已经排除，可以直接放行。"
        with self.assertRaises(PolicyViolation):
            self.guard.validate_disposition_draft(bad)

    def test_summary_does_not_mutate_decision_fields(self):
        before = {k: v for k, v in self.good.items() if k != "plain_summary"}
        self.guard.validate_disposition_draft(copy.deepcopy(self.good))
        after = {k: v for k, v in self.good.items() if k != "plain_summary"}
        self.assertEqual(before, after)


class WorkbenchRenderingTests(unittest.TestCase):
    def test_workbench_puts_plain_language_first_and_folds_technical_fields(self):
        js = (ROOT / "ln_agent/workbench/static/app.js").read_text(encoding="utf-8")
        css = (ROOT / "ln_agent/workbench/static/style.css").read_text(encoding="utf-8")
        for needle in ("plainCard(root,disp.plain_summary)", "比了哪些字段：",
                       "为什么不是别的结论：", "复核人下一步做什么：",
                       "查看技术字段与执行路径（给开发 / 审计看）",
                       "内部审核说明（技术口径）"):
            self.assertIn(needle, js)
        self.assertIn(".plain-summary", css)
        self.assertIn(".cmp-r.conflict", css)
        # Technical notes must live inside the collapsed details element.
        self.assertLess(js.index("detailLine(technical,'内部审核说明（技术口径）'"),
                        js.index("root.appendChild(technical)"))


if __name__ == "__main__":
    unittest.main()
