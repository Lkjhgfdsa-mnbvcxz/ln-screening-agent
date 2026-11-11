"""Regression: every unresolved hit must carry an individually usable reason.

Found on 8 authorized real checklists: the BOSS 记录源 / 分数 / ID号码 columns
were dropped by the local capture script, and build_disposition() collapsed 150+
unresolved hits into one identical sentence. Those are fixed here without
touching any conclusion, recommendation or rule. All fixtures are synthetic.
"""
from __future__ import annotations

import unittest

from ln_agent import Case, FixtureResearchTool, Orchestrator, Policy


def _fact(side: str, field: str, value: str, eid: str) -> dict:
    return {"side": side, "field": field, "value": value,
            "evidence_id": eid, "origin": "kyb_verified" if side == "applicant" else "ln_structured",
            "checked": True}


def _case(risk_event: dict, *, name: str = "Synth, Person") -> dict:
    return {
        "case_id": "SYN-REASON-001",
        "subjects": [{
            "subject_id": "S1", "entity_type": "person", "role": "applicant",
            "facts": [_fact("applicant", "name", "合成对象", "SYN-REASON-001:app:name")],
        }],
        "hits": [{
            "hit_id": "H1", "subject_id": "S1", "category": "执法",
            "entity_type": "person",
            "facts": [_fact("hit", "name", name, "SYN-REASON-001:H1:ln:name")],
            "research_keys": [],
            "risk_event": risk_event,
        }],
    }


def _run(risk_event: dict) -> dict:
    return Orchestrator(Policy(), FixtureResearchTool({})).run(
        Case.from_dict(_case(risk_event)))["results"][0]


class PerHitReasonTests(unittest.TestCase):
    def _event(self, *, domain: str, missing: str) -> dict:
        return {
            "summary": f"LN 记录载明执法类命中，记录源指向 {domain}；来源未独立核验。",
            "severity": "high",
            "source_ref": f"https://{domain}/synthetic-record",
            "material_context": [
                {"evidence_id": "SYN-REASON-001:H1:ln:source",
                 "text": f"记录源 6 条，主域名 {domain}；原页可达性未核验"},
                {"evidence_id": "SYN-REASON-001:H1:ln:id",
                 "text": f"命中侧仅有 LN 记录号 {missing}，无证件号/生日，无法证件级比对"},
            ],
        }

    def test_unresolved_hit_reason_includes_source_and_missing_fields(self):
        r = _run(self._event(domain="synthetic-12309.example", missing="7456984"))
        d = r["disposition"]
        self.assertIsNone(d["business_conclusion"])
        self.assertEqual(d["recommendation"], "INSUFFICIENT_EVIDENCE_RECORDED")
        self.assertIn("无法确定是否命中", d["internal_note"])
        self.assertIn("synthetic-12309.example", d["internal_note"])
        self.assertIn("无证件号/生日", d["internal_note"])
        self.assertFalse(d["automatically_sent"])
        self.assertFalse(d["automatically_cleared"])

    def test_two_hits_with_different_sources_get_different_reasons(self):
        a = _run(self._event(domain="source-a.example", missing="7000001"))
        b = _run(self._event(domain="source-b.example", missing="7000002"))
        self.assertNotEqual(a["disposition"]["internal_note"],
                            b["disposition"]["internal_note"])

    def test_reason_never_claims_false_positive_or_clearance(self):
        d = _run(self._event(domain="source-c.example", missing="7000003"))["disposition"]
        for forbidden in ("误报", "已放行", "自动排除", "确认未命中"):
            self.assertNotIn(forbidden, d["internal_note"])
        self.assertIn("不可据此判为未命中", d["internal_note"])

    def test_no_source_ref_stays_short_and_unreported(self):
        d = _run({"summary": "无来源", "severity": "high"})["disposition"]
        self.assertIsNone(d["business_conclusion"])
        self.assertFalse(d["report_recommended"])
        self.assertNotIn("补充：", d["internal_note"])

    def test_report_draft_has_no_double_full_stop(self):
        # A strong-link case still takes the original report-draft branch.
        event = self._event(domain="source-d.example", missing="7000004")
        event["severity"] = "critical"
        case = _case(event, name="合成对象")
        case["hits"][0]["facts"].append(
            _fact("hit", "dob", "1990-01-01", "SYN-REASON-001:H1:ln:dob"))
        case["subjects"][0]["facts"].append(
            _fact("applicant", "dob", "1990-01-01", "SYN-REASON-001:app:dob"))
        # Romanized hit name vs Chinese applicant name is enough here: the
        # source-attributed critical event path must not emit "。。".
        r = Orchestrator(Policy(), FixtureResearchTool({})).run(Case.from_dict(case))["results"][0]
        self.assertNotIn("。。", r["disposition"]["internal_note"])


if __name__ == "__main__":
    unittest.main()
