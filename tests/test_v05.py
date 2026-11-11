"""V0.5 independent source corroboration, durable review, REOPEN and boundaries.
All sources, authorizations, people and cases are synthetic.
"""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ln_agent import Case, Policy
from ln_agent.corroboration import assess_corroboration
from ln_agent.document_intelligence import DocumentIntelligence, parse_document
from ln_agent.document_tools import DocumentFixtureResearchTool
from ln_agent.fact_verification import FactVerifier, ReviewAttestation
from ln_agent.review_store import ReviewStore
from ln_agent.review_service import PersistentReviewService

DOCS = {
    "doc-a": {"data":"张宏于1998年担任某银行副行长。\n机构资料。".encode(),"content_type":"text/plain","source_url":"https://a.example.invalid/1998","publisher":"机构甲"},
    "doc-b": {"data":"张宏于1998年担任某银行副行长。\n其他独立文件。".encode(),"content_type":"text/plain","source_url":"https://b.example.invalid/1998","publisher":"机构乙"},
    "doc-c": {"data":"张宏于1999年担任某银行副行长。\n独立记录。".encode(),"content_type":"text/plain","source_url":"https://c.example.invalid/1999","publisher":"机构丙"},
}


def make_case(case_id="C1",hit_ids=("H1",), doc_ids=("doc-a","doc-b")):
    subject={"subject_id":"P1","entity_type":"person","role":"director","facts":[
        {"side":"applicant","field":"name","value":"张宏","evidence_id":"kyb-name","origin":"kyb_verified","checked":True},
        {"side":"applicant","field":"dob","value":"2002-01-01","evidence_id":"kyb-dob","origin":"kyb_verified","checked":True}]}
    hits=[{"hit_id":h,"subject_id":"P1","category":"enforcement","entity_type":"person",
        "facts":[{"side":"hit","field":"name","value":"张宏","evidence_id":f"ln-{h}","origin":"ln_structured","checked":True}],
        "research_keys":[f"doc:{d}" for d in doc_ids]} for h in hit_ids]
    return Case.from_dict({"case_id":case_id,"subjects":[subject],"hits":hits})


def parsed_and_packet(doc_id):
    x=DOCS[doc_id]
    doc=parse_document(x["data"],document_id=doc_id,content_type="text/plain",
                       source_url=x["source_url"], publisher=x["publisher"])
    packet=DocumentIntelligence().analyze(doc,["张宏"]).to_dict()
    assert len(packet["extracted_fact_candidates"])==1, packet["extracted_fact_candidates"]
    return doc, packet


def signed(case_id="C1",hit_id="H1",doc_id="doc-a",origin="ORIGIN-A",year="1998",
           reviewer="human-A",claim="EVENT-ROLE-1998",independent=True):
    doc, packet=parsed_and_packet(doc_id)
    candidate=packet["extracted_fact_candidates"][0]
    assert candidate["value"]==year
    return ReviewAttestation(case_id=case_id,hit_id=hit_id,document_id=doc_id,
        source_sha256=doc.sha256,candidate_id=candidate["candidate_id"],
        reviewer_id=reviewer,event_context="held_position",
        source_authenticated=True,person_attributed_to_hit=True,event_meaning_checked=True,
        source_content_checked=True,conflicting_material_reviewed=True,
        note="SYNTHETIC HUMAN REVIEW",claim_id=claim,
        source_origin_id=origin,source_independence_checked=independent)


def verify_records(atts):
    out=[]
    for a in atts:
        doc,p=parsed_and_packet(a.document_id)
        result=FactVerifier(attestations=[a],authorized_reviewers=frozenset({"human-A"})).verify_packet(
            case_id=a.case_id,hit_id=a.hit_id,document=doc,packet=p)
        out += result.verification_records
    return out


class TestCorroboration(unittest.TestCase):
    def test_two_independent_attested_sources_corroborate(self):
        atts=[signed(),signed(doc_id="doc-b",origin="ORIGIN-B")]
        result=assess_corroboration(case_id="C1",hit_id="H1",records=verify_records(atts))
        self.assertEqual(result[0].status,"CORROBORATED")
        self.assertEqual(result[0].independent_groups,2)
        self.assertEqual(result[0].values,("1998",))

    def test_two_links_same_original_not_independent(self):
        atts=[signed(),signed(doc_id="doc-b",origin="ORIGIN-A")]
        r=assess_corroboration(case_id="C1",hit_id="H1",records=verify_records(atts))
        self.assertEqual(r[0].status,"SINGLE_SOURCE")
        self.assertEqual(r[0].independent_groups,1)

    def test_unknown_lineage_cannot_claim_independence(self):
        atts=[signed(),signed(doc_id="doc-b",origin="",independent=False)]
        r=assess_corroboration(case_id="C1",hit_id="H1",records=verify_records(atts))
        self.assertEqual(r[0].status,"LINEAGE_UNVERIFIED")

    def test_conflicting_years_same_reviewed_event_block(self):
        atts=[signed(),signed(doc_id="doc-c",origin="ORIGIN-C",year="1999")]
        r=assess_corroboration(case_id="C1",hit_id="H1",records=verify_records(atts))
        self.assertEqual(r[0].status,"CONTRADICTORY_SOURCES")
        self.assertEqual(set(r[0].values),{"1998","1999"})

    def test_different_claim_ids_not_forced_into_one_event(self):
        atts=[signed(),signed(doc_id="doc-c",origin="ORIGIN-C",year="1999",claim="EVENT-1999-OTHER")]
        r=assess_corroboration(case_id="C1",hit_id="H1",records=verify_records(atts))
        self.assertEqual(len(r),2)
        self.assertTrue(all(x.status=="SINGLE_SOURCE" for x in r))

    def test_different_hit_cannot_reuse_review(self):
        r=assess_corroboration(case_id="C1",hit_id="H2",records=verify_records([signed()]))
        self.assertEqual(r,[])

    def test_different_case_cannot_reuse_review(self):
        r=assess_corroboration(case_id="C2",hit_id="H1",records=verify_records([signed()]))
        self.assertEqual(r,[])

    def test_unverified_candidates_not_counted(self):
        r=assess_corroboration(case_id="C1",hit_id="H1",records=[
           {"case_id":"C1","hit_id":"H1","status":"PENDING_HUMAN_VERIFICATION",
            "verification_id":"VR-fake","claim_id":"abc","field":"acted_in_year",
            "value":"1998","source_origin_id":"ORIGIN-A","source_independence_checked":True}])
        self.assertEqual(r,[])

    def test_threshold_at_least_two(self):
        with self.assertRaises(ValueError):
            assess_corroboration(case_id="C1",hit_id="H1",records=[],minimum_independent_sources=1)

    def test_multiple_citations_same_origin_do_not_count_twice(self):
        one=verify_records([signed()])[0]
        two=dict(one, verification_id="VR-another",evidence_id="another-location")
        r=assess_corroboration(case_id="C1",hit_id="H1",records=[one,two])
        self.assertEqual(r[0].independent_groups,1)


class TestCrossSourceRouter(unittest.TestCase):
    def run_case(self, docs=("doc-a","doc-b"), atts=(), require=True):
        tool=DocumentFixtureResearchTool({d:DOCS[d] for d in docs})
        from ln_agent import Orchestrator
        from ln_agent.policy import Policy
        return Orchestrator(Policy(require_independent_corroboration_for_document_facts=require),
            tool,verification_attestations=list(atts),
            authorized_reviewers=frozenset({"human-A"})).run(make_case(doc_ids=docs))["results"][0]

    def test_two_independent_sources_enable_previous_hard_rule(self):
        r=self.run_case(atts=[signed(),signed(doc_id="doc-b",origin="ORIGIN-B")])
        self.assertEqual(r["route"],"EXCLUSION_CANDIDATE")
        self.assertEqual(r["corroboration"][0]["status"],"CORROBORATED")
        self.assertFalse(r["exclusion_authorized"])

    def test_one_source_verified_two_required_stops(self):
        r=self.run_case(atts=[signed()])
        self.assertEqual(r["route"],"FACT_CORROBORATION_REVIEW")
        self.assertFalse(r["exclusion_evidence_detected"])

    def test_mirrored_source_stops(self):
        r=self.run_case(atts=[signed(),signed(doc_id="doc-b",origin="ORIGIN-A")])
        self.assertEqual(r["route"],"FACT_CORROBORATION_REVIEW")
        self.assertEqual(r["corroboration"][0]["independent_groups"],1)

    def test_conflicting_sources_beat_temporal_rule(self):
        r=self.run_case(docs=("doc-a","doc-c"),atts=[signed(),signed(doc_id="doc-c",origin="ORIGIN-C",year="1999")])
        self.assertEqual(r["route"],"EVIDENCE_CONFLICT_REVIEW")
        self.assertFalse(r["exclusion_evidence_detected"])

    def test_unreviewed_second_source_not_counted(self):
        r=self.run_case(atts=[signed()])
        self.assertNotEqual(r["route"],"EXCLUSION_CANDIDATE")

    def test_optional_corroboration_policy_runtime_toggle(self):
        r=self.run_case(atts=[signed()],require=False)
        self.assertEqual(r["route"],"EXCLUSION_CANDIDATE")


class TestReviewStore(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"review.sqlite3"
        self.store=ReviewStore(self.path,authorized_reviewers=frozenset({"human-A"}))
        self.store.register_hit(case_id="C1",hit_id="H1",policy_version="V0.5")

    def tearDown(self): self.tmp.cleanup()

    def submit(self,att=None,hit="H1"):
        att=att or signed()
        doc,packet=parsed_and_packet(att.document_id)
        return self.store.submit_review(case_id="C1",hit_id=hit,attestation=att,document=doc,packet=packet)

    def test_reopen_increments_revision_and_makes_old_reviews_inactive(self):
        self.submit()
        self.assertEqual(len(self.store.active_attestations("C1","H1")),1)
        newrev=self.store.reopen(case_id="C1",hit_id="H1",reviewer_id="human-A",
            reason="NEW_DOCUMENT",new_material_refs=["new:doc-c"])
        self.assertEqual(newrev,2)
        self.assertEqual(self.store.active_attestations("C1","H1"),[])
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM attestations").fetchone()[0],1)

    def test_reopen_requires_real_reason_and_material_reference(self):
        with self.assertRaises(ValueError):
            self.store.reopen(case_id="C1",hit_id="H1",reviewer_id="human-A",
               reason="JUST_BECAUSE",new_material_refs=["doc-c"])
        with self.assertRaises(ValueError):
            self.store.reopen(case_id="C1",hit_id="H1",reviewer_id="human-A",
               reason="NEW_DOCUMENT",new_material_refs=[])

    def test_unauthorized_reopen_rejected(self):
        with self.assertRaises(PermissionError):
            self.store.reopen(case_id="C1",hit_id="H1",reviewer_id="external",
                reason="NEW_DOCUMENT",new_material_refs=["doc-c"])

    def test_submit_attestation_provenance_validated_before_db(self):
        bad=signed(origin="ORIGIN-A")
        from dataclasses import replace
        bad=replace(bad,source_sha256="0"*64)
        with self.assertRaises(ValueError):self.submit(bad)
        self.assertEqual(self.store.active_attestations("C1","H1"),[])

    def test_unauthorized_approval_rejected(self):
        with self.assertRaises(PermissionError):
            self.submit(signed(reviewer="other"))

    def test_attestation_other_hit_not_accepted(self):
        self.store.register_hit(case_id="C1",hit_id="H2",policy_version="V0.5")
        with self.assertRaises(ValueError):
            self.submit(hit="H2")

    def test_cannot_register_same_hit_with_different_policy_without_reopen(self):
        with self.assertRaises(ValueError):
            self.store.register_hit(case_id="C1",hit_id="H1",policy_version="V0.6")

    def test_duplicate_approval_not_silently_overwritten(self):
        self.submit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.submit()

    def test_decisions_append_and_become_historical_after_reopen(self):
        decision={"hit_id":"H1","route":"FACT_VERIFICATION_REVIEW","disposition_flags":[]}
        self.store.save_decision(case_id="C1",hit_id="H1",decision=decision)
        self.store.save_decision(case_id="C1",hit_id="H1",decision=decision)
        self.store.reopen(case_id="C1",hit_id="H1",reviewer_id="human-A",
            reason="NEW_DOCUMENT",new_material_refs=["doc-c"])
        decision2=dict(decision,route="EVIDENCE_CONFLICT_REVIEW")
        self.store.save_decision(case_id="C1",hit_id="H1",decision=decision2)
        versions=self.store.decisions("C1","H1")
        self.assertEqual([(r["revision"],r["seq"],r["historical"]) for r in versions],
                         [(1,1,True),(1,2,True),(2,1,False)])
        self.assertTrue(self.store.verify_local_audit_chain("C1","H1"))

    def test_reopen_policy_version_can_change_explicitly(self):
        self.store.reopen(case_id="C1",hit_id="H1",reviewer_id="human-A",
            reason="SOURCE_REVISION",new_material_refs=["doc-c"],new_policy_version="V0.6")
        self.assertEqual(self.store.register_hit(case_id="C1",hit_id="H1",policy_version="V0.6"),2)

    def test_database_persists_across_new_store_instance(self):
        self.submit()
        other=ReviewStore(self.path,authorized_reviewers=frozenset({"human-A"}))
        self.assertEqual(other.revision("C1","H1"),1)
        self.assertEqual(len(other.active_attestations("C1","H1")),1)
        self.assertTrue(other.verify_local_audit_chain("C1","H1"))

    def test_audit_event_mutation_detected(self):
        self.submit()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE review_events SET event_type='TAMPERED' WHERE event_type='HUMAN_REVIEW_ACCEPTED'")
        self.assertFalse(self.store.verify_local_audit_chain("C1","H1"))

    def test_sqlite_online_backup(self):
        self.submit()
        backup=Path(self.tmp.name)/"backup.sqlite3"
        self.store.backup(backup)
        restored=ReviewStore(backup,authorized_reviewers=frozenset({"human-A"}))
        self.assertEqual(len(restored.active_attestations("C1","H1")),1)
        self.assertTrue(restored.verify_local_audit_chain("C1","H1"))

    def test_case_scoping_and_hit_scoping(self):
        self.submit()
        self.store.register_hit(case_id="C2",hit_id="H1",policy_version="V0.5")
        self.store.register_hit(case_id="C1",hit_id="H2",policy_version="V0.5")
        self.assertEqual(self.store.active_attestations("C2","H1"),[])
        self.assertEqual(self.store.active_attestations("C1","H2"),[])

    def test_decision_wrong_hit_rejected(self):
        with self.assertRaises(ValueError):
            self.store.save_decision(case_id="C1",hit_id="H1",decision={"hit_id":"H2"})

    def test_changed_ln_input_requires_reopen_and_fresh_snapshot(self):
        service=PersistentReviewService(self.store,Policy(version="V0.5"),
            DocumentFixtureResearchTool(DOCS))
        service.run_case(make_case(doc_ids=("doc-a",)))
        with self.assertRaisesRegex(ValueError, "REOPEN"):
            service.run_case(make_case(doc_ids=("doc-b",)))
        self.store.reopen(case_id="C1",hit_id="H1",reviewer_id="human-A",
            reason="NEW_DOCUMENT",new_material_refs=["doc-b"])
        result=service.run_case(make_case(doc_ids=("doc-b",)))
        self.assertEqual(result["results"][0]["review_revision"],2)

    def test_changed_applicant_dob_requires_reopen(self):
        service=PersistentReviewService(self.store,Policy(version="V0.5"),
            DocumentFixtureResearchTool(DOCS))
        case=make_case()
        service.run_case(case)
        changed=make_case()
        from dataclasses import replace
        original=changed.subjects[0].facts[1]
        changed.subjects[0].facts[1]=replace(original,value="2003-02-01")
        with self.assertRaisesRegex(ValueError,"REOPEN"):
            service.run_case(changed)

    def test_service_reopen_reruns_without_old_attestations(self):
        self.submit(signed())
        self.submit(signed(doc_id="doc-b",origin="ORIGIN-B"))
        tool=DocumentFixtureResearchTool(DOCS)
        policy=Policy(version="V0.5",require_independent_corroboration_for_document_facts=True)
        service=PersistentReviewService(self.store,policy,tool)
        case=make_case()
        result=service.run_case(case)["results"][0]
        self.assertEqual(result["route"],"EXCLUSION_CANDIDATE")
        self.assertEqual(result["review_revision"],1)
        self.store.reopen(case_id="C1",hit_id="H1",reviewer_id="human-A",
            reason="NEW_DOCUMENT",new_material_refs=["doc-c"])
        # The original two approvals remain historical only; new revision
        # requires explicit fresh verification of the changed evidence set.
        result2=service.run_case(case)["results"][0]
        self.assertEqual(result2["review_revision"],2)
        self.assertEqual(result2["route"],"FACT_VERIFICATION_REVIEW")
        self.assertEqual(len(self.store.decisions("C1","H1")),2)
        self.assertTrue(self.store.decisions("C1","H1")[0]["historical"])
        self.assertTrue(self.store.verify_local_audit_chain("C1","H1"))


if __name__=="__main__": unittest.main()
