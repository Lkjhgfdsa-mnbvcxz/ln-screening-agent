"""Execute V0.5 source corroboration and REOPEN on wholly fabricated fixtures.

The script creates a fresh temporary SQLite database. The reviewer is a code
fixture; there is NO real human identity verification or corporate approval.
"""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ln_agent.corroboration import assess_corroboration
from ln_agent.document_intelligence import DocumentIntelligence, parse_document
from ln_agent.document_tools import DocumentFixtureResearchTool
from ln_agent.fact_verification import ReviewAttestation, FactVerifier
from ln_agent.policy import Policy
from ln_agent.review_service import PersistentReviewService
from ln_agent.review_store import ReviewStore
from ln_agent.models import Case

ROOT=Path(__file__).resolve().parent
DATA={
 "a":{"data":"张宏于1998年担任某银行副行长。\n来源 A。".encode(),"content_type":"text/plain","source_url":"https://a.example.invalid/item","publisher":"模拟机构甲"},
 "b":{"data":"张宏于1998年担任某银行副行长。\n来源 B 独立记录。".encode(),"content_type":"text/plain","source_url":"https://b.example.invalid/item","publisher":"模拟机构乙"},
 "c":{"data":"张宏于1999年担任某银行副行长。\n来源 C 记载不同时间。".encode(),"content_type":"text/plain","source_url":"https://c.example.invalid/item","publisher":"模拟机构丙"},
}

def parse(docid):
    rec=DATA[docid]
    doc=parse_document(rec["data"],document_id=docid,content_type="text/plain",
        source_url=rec["source_url"],publisher=rec["publisher"])
    packet=DocumentIntelligence().analyze(doc,["张宏"]).to_dict()
    return doc,packet

def make_review(docid,origin):
    doc,p=parse(docid)
    c=p["extracted_fact_candidates"][0]
    return ReviewAttestation(case_id="DEMO-C",hit_id="DEMO-H",document_id=docid,
        source_sha256=doc.sha256,candidate_id=c["candidate_id"],reviewer_id="DEMO-REVIEWER",
        event_context="held_position",source_authenticated=True,
        person_attributed_to_hit=True,event_meaning_checked=True,
        source_content_checked=True,conflicting_material_reviewed=True,
        note="DEMO ONLY: fictional human check",claim_id="CLAIM-ROLE-001",
        source_origin_id=origin,source_independence_checked=True)

def case(ids):
    return Case.from_dict({"case_id":"DEMO-C","subjects":[
        {"subject_id":"DEMO-P","entity_type":"person","role":"director","facts":[
         {"side":"applicant","field":"name","value":"张宏","evidence_id":"kyb:name","origin":"kyb_verified","checked":True},
         {"side":"applicant","field":"dob","value":"2002-01-01","evidence_id":"kyb:dob","origin":"kyb_verified","checked":True}]}],
       "hits":[{"hit_id":"DEMO-H","subject_id":"DEMO-P","category":"enforcement",
          "entity_type":"person","facts":[
            {"side":"hit","field":"name","value":"张宏","evidence_id":"ln:name","origin":"ln_structured","checked":True}],
          "research_keys":["doc:"+x for x in ids]}]})

def main():
    policy=Policy(version="DEMO-0.5",require_independent_corroboration_for_document_facts=True)
    with TemporaryDirectory() as d:
        store=ReviewStore(Path(d)/"review.sqlite3",authorized_reviewers=frozenset({"DEMO-REVIEWER"}))
        service=PersistentReviewService(store,policy,DocumentFixtureResearchTool(DATA))
        input_case=case(["a","b"])
        before=service.run_case(input_case)["results"][0]
        for docid,origin in (("a","original-official-A"),("b","original-record-B")):
            att=make_review(docid,origin);doc,p=parse(docid)
            store.submit_review(case_id="DEMO-C",hit_id="DEMO-H",attestation=att,document=doc,packet=p)
        corroborated=service.run_case(input_case)["results"][0]
        store.reopen(case_id="DEMO-C",hit_id="DEMO-H",reviewer_id="DEMO-REVIEWER",
            reason="NEW_DOCUMENT",new_material_refs=["c"])
        reopened=service.run_case(case(["a","c"]))["results"][0]
        active_after_reopen=len(store.active_attestations("DEMO-C","DEMO-H"))
        for docid,origin in (("a","original-official-A"),("c","original-record-C")):
            att=make_review(docid,origin);doc,p=parse(docid)
            store.submit_review(case_id="DEMO-C",hit_id="DEMO-H",attestation=att,document=doc,packet=p)
        conflict=service.run_case(case(["a","c"]))["results"][0]
        mirror_att=[make_review("a","shared-original"),make_review("b","shared-original")]
        mirror_records=[]
        for att in mirror_att:
            doc,p=parse(att.document_id)
            mirror_records.extend(FactVerifier(attestations=[att],authorized_reviewers=frozenset({"DEMO-REVIEWER"})).verify_packet(
                case_id="DEMO-C",hit_id="DEMO-H",document=doc,packet=p).verification_records)
        mirror=assess_corroboration(case_id="DEMO-C",hit_id="DEMO-H",records=mirror_records)[0]
        report={"notice":"SYNTHETIC DATA AND SYNTHETIC HUMAN SIGN-OFF; NO ACTUAL LN/REGULATORY REVIEW",
          "policy":{"require_independent_corroboration_for_document_facts":True,"minimum_independent_sources":2},
          "before":{"route":before["route"],"corroboration":before["corroboration"]},
          "two_independent_sources":{"route":corroborated["route"],"corroboration":corroborated["corroboration"],
                                    "exclusion_authorized":corroborated["exclusion_authorized"]},
          "after_reopen":{"route":reopened["route"],"review_revision":reopened["review_revision"],
                          "active_attestations":active_after_reopen},
          "after_new_conflicting_source":{"route":conflict["route"],"corroboration":conflict["corroboration"]},
          "mirrored_material":{"status":mirror.status,"independent_groups":mirror.independent_groups},
          "decision_history":[{"revision":x["revision"],"historical":x["historical"],
             "route":x["decision"]["route"]} for x in store.decisions("DEMO-C","DEMO-H")],
          "audit_chain_valid_in_demo":store.verify_local_audit_chain("DEMO-C","DEMO-H")}
        outfile=ROOT/"examples"/"v05_demo_report.json"
        outfile.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print("before:",before["route"])
        print("two independent:",corroborated["route"])
        print("after REOPEN:",reopened["route"])
        print("conflicting new source:",conflict["route"])
        print("same-origin mirrors:",mirror.status)
        print("audit chain valid:",report["audit_chain_valid_in_demo"])
        print("report:",outfile)

if __name__=="__main__":main()
