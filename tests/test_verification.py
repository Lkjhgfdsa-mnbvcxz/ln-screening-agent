"""Cross-condition tests: evidence citation is not the same as verified identity."""
import unittest
from dataclasses import replace
from ln_agent import Case, Policy, Orchestrator
from ln_agent.models import Fact, Hit, Subject
from ln_agent.document_tools import DocumentFixtureResearchTool
from ln_agent.document_intelligence import parse_document, DocumentIntelligence
from ln_agent.fact_verification import FactVerifier, ReviewAttestation
from ln_agent.policy_guard import PolicyGuard, PolicyViolation
from ln_agent.skills import get_skill
from ln_agent.evidence import evaluate

SOURCE = ("第一章 人员资料\n张宏于1998年担任某银行副行长。\n"
          "第二章 其他人员\n另一名张宏出生日期不明。\n"
          "第三章 更正\n更正：原名单人员记录部分存在错误，详见附件。\n").encode()
DOCID = "notice"


def build_document():
    return parse_document(SOURCE, document_id=DOCID, content_type="text/plain",
                          source_url="https://example.invalid/fixture", title="合成公告",
                          publisher="测试机构", document_number="TEST-1")


def build_candidate():
    d=build_document()
    return d, DocumentIntelligence().analyze(d,["张宏"]).to_dict()


def attestation(case="c1",hit="h1",candidate_id=None,**changes):
    d,p=build_candidate()
    values=dict(case_id=case,hit_id=hit,document_id=DOCID,source_sha256=d.sha256,
        candidate_id=candidate_id or p["extracted_fact_candidates"][0]["candidate_id"],
        reviewer_id="human-A",event_context="held_position",
        source_authenticated=True,person_attributed_to_hit=True,
        event_meaning_checked=True,source_content_checked=True,
        conflicting_material_reviewed=True,note="离线测试：人工逐项核对")
    values.update(changes)
    return ReviewAttestation(**values)


def make_case(case="c1",hit="h1",category="enforcement"):
    subj=Subject("person-1","person","董事",[
        Fact("applicant","name","张宏","kyb:name","kyb_verified",True),
        Fact("applicant","dob","2002-01-01","kyb:dob","kyb_verified",True)])
    alert=Hit(hit,"person-1",category,"person",facts=[
        Fact("hit","name","张宏","ln:name","ln_structured",True)], research_keys=["doc:notice"])
    return Case(case,[subj],[alert])


def run(case=None,approvals=(),reviewers=frozenset({"human-A"})):
    tool=DocumentFixtureResearchTool({DOCID:{"data":SOURCE,"content_type":"text/plain",
                             "source_url":"https://example.invalid/fixture","publisher":"测试机构"}})
    report=Orchestrator(Policy(),tool,verification_attestations=list(approvals),
                         authorized_reviewers=reviewers).run(case or make_case())
    return report["results"][0]


class TestVerifiedDocumentFacts(unittest.TestCase):
    def test_document_alone_never_excludes(self):
        result=run()
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")
        self.assertFalse(result["exclusion_evidence_detected"])
        self.assertIsNone(result["suspicion"])
        self.assertIn("PENDING_HUMAN_VERIFICATION",
                      [x["status"] for x in result["verification_records"]])

    def test_authorized_complete_attestation_rechecks_rule(self):
        result=run(approvals=[attestation()])
        self.assertEqual(result["route"],"EXCLUSION_CANDIDATE")
        self.assertIn("PRE_BIRTH_ACTION_IMPOSSIBLE",result["reasons"])
        self.assertTrue(result["exclusion_evidence_detected"])
        self.assertFalse(result["exclusion_authorized"])
        self.assertTrue(any(x["status"]=="VERIFIED_FOR_COMPARISON" for x in result["verification_records"]))
        self.assertTrue(any(x["applicability_checked"] for x in result["hit_evidence_links"]))

    def test_unapproved_reviewer_cannot_promote(self):
        result=run(approvals=[attestation()],reviewers=frozenset())
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")
        self.assertIn("UNAUTHORIZED_REVIEWER",result["verification_records"][0]["reasons"])

    def test_wrong_hit_attestation_not_inherited(self):
        result=run(make_case(hit="h2"),approvals=[attestation(hit="h1")])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")

    def test_wrong_case_attestation_not_inherited(self):
        result=run(make_case(case="c2"),approvals=[attestation(case="c1")])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")

    def test_source_hash_mismatch_rejected(self):
        result=run(approvals=[attestation(source_sha256="0"*64)])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")
        self.assertIn("ATTESTATION_SOURCE_MISMATCH",result["verification_records"][0]["reasons"])

    def test_no_source_authenticity_no_promote(self):
        result=run(approvals=[attestation(source_authenticated=False)])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")
        self.assertIn("SOURCE_UNAUTHENTICATED",result["verification_records"][0]["reasons"])

    def test_no_entity_attribution_no_promote(self):
        result=run(approvals=[attestation(person_attributed_to_hit=False)])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")
        self.assertIn("HIT_ENTITY_NOT_ATTRIBUTED",result["verification_records"][0]["reasons"])

    def test_event_semantics_not_verified(self):
        result=run(approvals=[attestation(event_meaning_checked=False)])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")

    def test_source_content_unverified(self):
        result=run(approvals=[attestation(source_content_checked=False)])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")

    def test_correction_not_reviewed_blocks(self):
        result=run(approvals=[attestation(conflicting_material_reviewed=False)])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")
        self.assertIn("CORRECTION_OR_RETRACTION_UNRESOLVED",result["verification_records"][0]["reasons"])

    def test_context_not_on_whitelist(self):
        result=run(approvals=[attestation(event_context="publication_year")])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")

    def test_wrong_candidate_digest_not_accepted(self):
        result=run(approvals=[attestation(candidate_id="FC-invalid")])
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")

    def test_quote_tamper_detected_without_review(self):
        d,p=build_candidate();p["extracted_fact_candidates"][0]["evidence_quote"]="张宏于1997年担任银行副行长"
        o=FactVerifier().verify_packet(case_id="c1",hit_id="h1",document=d,packet=p)
        self.assertEqual(o.verification_records[0]["status"],"REJECTED_PROVENANCE")

    def test_block_location_tamper_detected(self):
        d,p=build_candidate();p["evidence_spans"][0]["block_index"]=999
        o=FactVerifier().verify_packet(case_id="c1",hit_id="h1",document=d,packet=p)
        self.assertEqual(o.verification_records[0]["status"],"REJECTED_PROVENANCE")

    def test_source_snapshot_tamper_detected(self):
        d,p=build_candidate();p["sha256"]="bad"
        o=FactVerifier().verify_packet(case_id="c1",hit_id="h1",document=d,packet=p)
        self.assertEqual(o.verification_records[0]["status"],"REJECTED_PROVENANCE")

    def test_model_cannot_submit_reviewer_verified_fact(self):
        f=Fact("hit","acted_in_year","1998","fake","reviewer_verified",True,
               "held_position",verification_id="VR-forged")
        with self.assertRaises(PolicyViolation):
            PolicyGuard(Policy()).validate_facts([f],get_skill("person"))
        app=[Fact("applicant","dob","2002-01-01","a","kyb_verified",True)]
        self.assertFalse(evaluate(app,[f],"person").exclusion_rules)

    def test_verification_id_required_in_evidence_engine(self):
        f=Fact("hit","acted_in_year","1998","e","reviewer_verified",True,
               "held_position",verification_id="VR-confirmed")
        app=[Fact("applicant","dob","2002-01-01","a","kyb_verified",True)]
        self.assertFalse(evaluate(app,[f],"person").exclusion_rules)
        self.assertIn("PRE_BIRTH_ACTION_IMPOSSIBLE",
                      evaluate(app,[f],"person",frozenset({"VR-confirmed"})).exclusion_rules)

    def test_verification_not_equal_approved_disposition(self):
        r=run(approvals=[attestation()])
        self.assertFalse(r["exclusion_authorized"])
        self.assertTrue(r["review_required"])

    def test_sanctions_review_survives_verified_exclusion(self):
        r=run(make_case(category="sanctions"),approvals=[attestation()])
        self.assertEqual(r["route"],"EXCLUSION_CANDIDATE")
        self.assertIn("SCREENING_REVIEW_REQUIRED",r["disposition_flags"])

    def test_two_hits_shared_doc_no_cross_approval(self):
        case=make_case();case.hits.append(Hit("h2","person-1","enforcement","person",
                             facts=[Fact("hit","name","张宏","ln:2","ln_structured",True)],
                             research_keys=["doc:notice"]))
        tool=DocumentFixtureResearchTool({DOCID:{"data":SOURCE,"content_type":"text/plain"}})
        result=Orchestrator(Policy(),tool,verification_attestations=[attestation()],
                 authorized_reviewers=frozenset({"human-A"})).run(case)
        routes={x["hit_id"]:x["route"] for x in result["results"]}
        self.assertEqual(routes["h1"],"EXCLUSION_CANDIDATE")
        self.assertEqual(routes["h2"],"FACT_VERIFICATION_REVIEW")
        self.assertEqual(tool.read_count,1)

    def test_duplicate_attestations_disallowed(self):
        with self.assertRaises(ValueError):
            FactVerifier(attestations=[attestation(),attestation()])

if __name__ == "__main__": unittest.main()

# Additional boundary tests: metadata binding and incomplete parse conditions.
class TestVerificationBinding(unittest.TestCase):
    def test_candidate_source_url_must_match_document(self):
        d,p=build_candidate()
        p["extracted_fact_candidates"][0]["source_url"]="https://other.invalid/altered"
        o=FactVerifier().verify_packet(case_id="c1",hit_id="h1",document=d,packet=p)
        self.assertEqual(o.verification_records[0]["status"],"REJECTED_PROVENANCE")

    def test_partial_parse_cannot_promote_without_manual_coverage_resolution(self):
        d,p=build_candidate()
        p["parse_warnings"].append("OCR_MAY_BE_REQUIRED")
        o=FactVerifier(attestations=[attestation()],authorized_reviewers=frozenset({"human-A"})).verify_packet(
            case_id="c1",hit_id="h1",document=d,packet=p)
        self.assertIn("INCOMPLETE_DOCUMENT_COVERAGE",o.verification_records[0]["reasons"])

    def test_wrong_document_id_in_attestation(self):
        r=run(approvals=[attestation(document_id="other-document")])
        self.assertEqual(r["route"],"FACT_VERIFICATION_REVIEW")
        self.assertIn("ATTESTATION_SOURCE_MISMATCH",r["verification_records"][0]["reasons"])

class TestDocumentCompleteness(unittest.TestCase):
    def test_material_sweep_truncation_blocks_manual_promotion(self):
        d,p=build_candidate();p["coverage"]["truncated_material_results"]=True
        o=FactVerifier(attestations=[attestation()],authorized_reviewers=frozenset({"human-A"})).verify_packet(
            case_id="c1",hit_id="h1",document=d,packet=p)
        self.assertIn("INCOMPLETE_DOCUMENT_COVERAGE",o.verification_records[0]["reasons"])

    def test_full_text_unavailable_blocks_promotion(self):
        d,p=build_candidate();p["coverage"]["full_text_read"]=False
        o=FactVerifier(attestations=[attestation()],authorized_reviewers=frozenset({"human-A"})).verify_packet(
            case_id="c1",hit_id="h1",document=d,packet=p)
        self.assertIn("INCOMPLETE_DOCUMENT_COVERAGE",o.verification_records[0]["reasons"])
