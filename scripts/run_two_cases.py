"""Offline acceptance: one strong-link hit and one false-positive candidate.

No real KYC or LN data; does not connect to any provider.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ln_agent import Case, Policy, Orchestrator, FixtureResearchTool

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "strong_link": ROOT / "examples/case_true_link.json",
    "false_positive": ROOT / "examples/case_false_positive.json",
}
EXPECTED = {"strong_link": "LINKED_RISK_REVIEW", "false_positive": "EXCLUSION_CANDIDATE"}

def run_pair():
    cases = {}
    for label, path in CASES.items():
        raw = json.loads(path.read_text(encoding="utf-8"))
        report = Orchestrator(Policy(), FixtureResearchTool()).run(Case.from_dict(raw))
        d = report["results"][0]
        assert d["route"] == EXPECTED[label], (label, d["route"])
        assert d["review_required"] is True
        assert d["exclusion_authorized"] is False
        assert d["gate"]["screening_alert_observed"] is True
        assert len(d["rule_findings"]) > 0
        assert len(d["explanation"]) >= 5
        cases[label] = {"input_case_file": str(path.relative_to(ROOT)), "report": report}
    return {"demo_type": "SYNTHETIC_OFFLINE_READ_ONLY", "assertions_passed": True,
            "warnings": ["STRONG_LINK is not final regulatory confirmation", "EXCLUSION_CANDIDATE is not approved clearance", "NO production sources or authenticated human review"],
            "cases": cases}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out", default="examples/two_case_demo_report.json")
    args=parser.parse_args()
    data=run_pair()
    target=ROOT / args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for label,info in data["cases"].items():
        d=info["report"]["results"][0]
        print(f"{label}: {d['route']} | identity={d['identity']} | report_draft={d['disposition']['report_recommended']} | manual_queue={d['disposition']['manual_queue_required']}")
    print("PASS: both independent synthetic cases; report:", target)

if __name__ == "__main__":
    main()
