"""Reproducible offline before/after manual verification demonstration.

ATTENTION: all documents, reviewers and attestations are synthetic fixtures.
No network calls or real human authentication are performed here.
"""
from __future__ import annotations
import json
from pathlib import Path
from ln_agent import Orchestrator, Policy, Case
from ln_agent.document_tools import DocumentFixtureResearchTool
from ln_agent.document_intelligence import DocumentIntelligence, parse_document
from ln_agent.fact_verification import ReviewAttestation

BASE = Path(__file__).resolve().parent
CASE_PATH = BASE / "examples" / "document_case.json"
DOCUMENT_PATH = BASE / "examples" / "documents" / "synthetic_penalty_notice.html"


def main():
    case=Case.from_dict(json.loads(CASE_PATH.read_text(encoding="utf-8")))
    data=DOCUMENT_PATH.read_bytes()
    docid="synthetic-penalty"
    source_url="https://example.invalid/official-fictional-penalty"
    record={"data":data,"content_type":"text/html","source_url":source_url,
            "title":"模拟处罚公告","publisher":"模拟机构"}
    doc=parse_document(data,document_id=docid,content_type="text/html",
                       source_url=source_url,title=record["title"],publisher=record["publisher"])
    # Identify candidate via actual parser, never guess its candidate_id/hash.
    p=DocumentIntelligence().analyze(doc,["张宏"])
    if not p.extracted_fact_candidates:
        raise RuntimeError("missing synthetic candidate")
    candidate=p.extracted_fact_candidates[0]
    hit=case.hits[0]
    if "doc:synthetic-penalty" not in hit.research_keys:
        hit.research_keys=["doc:synthetic-penalty"]
    before=Orchestrator(Policy(),DocumentFixtureResearchTool({docid:record})).run(case)
    # The following is a deliberate synthetic sign-off, NOT automatic approval.
    signed=ReviewAttestation(case_id=case.case_id,hit_id=hit.hit_id,
      document_id=docid,source_sha256=doc.sha256,
      candidate_id=candidate["candidate_id"],reviewer_id="DEMO-REVIEWER",
      event_context="held_position",source_authenticated=True,
      person_attributed_to_hit=True,event_meaning_checked=True,
      source_content_checked=True,conflicting_material_reviewed=True,
      note="DEMO ONLY: hypothetical complete human verification")
    after=Orchestrator(Policy(),DocumentFixtureResearchTool({docid:record}),
        verification_attestations=[signed],
        authorized_reviewers=frozenset({"DEMO-REVIEWER"})).run(case)
    report={"notice":"ALL SYNTHETIC - no LN access or actual human review",
            "before_human_verification":before,"after_synthetic_human_verification":after}
    out=BASE/"examples"/"verification_demo_report.json"
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for label,result in (("before",before),("after",after)):
        x=result["results"][0]
        print(label, x["route"],x["investigation_status"],
              "verified:",sum(r["status"]=="VERIFIED_FOR_COMPARISON" for r in x["verification_records"]))
    print(out)

if __name__ == "__main__":main()
