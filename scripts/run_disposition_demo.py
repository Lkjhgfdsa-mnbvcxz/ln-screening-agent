"""Two entirely fictional screening cases with concise internal/compliance drafts."""
from __future__ import annotations
import json
from pathlib import Path
from ln_agent import Case, Policy, Orchestrator, FixtureResearchTool

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=("case_company_critical_suspected.json", "case_person_identity_suspected.json")

def run_examples():
    results=[]
    for name in FIXTURES:
        data=json.loads((ROOT/"examples"/name).read_text(encoding="utf-8"))
        report=Orchestrator(Policy(),FixtureResearchTool()).run(Case.from_dict(data))
        decision=report["results"][0]
        results.append({"fixture":name,"route":decision["route"],"disposition":decision["disposition"],
                        "source_evidence":decision["evidence"],"read_only":report["read_only"]})
    return {"demo":"SYNTHETIC_ONLY_NO_REAL_COMPLIANCE_DISPOSITION","results":results}

def main():
    data=run_examples()
    for item in data["results"]:
        print("CASE:",item["fixture"])
        print("INTERNAL:",item["disposition"]["internal_note"])
        print("COMPLIANCE DRAFT:\n",item["disposition"]["compliance_message"])
        print("---")

if __name__=="__main__":main()
