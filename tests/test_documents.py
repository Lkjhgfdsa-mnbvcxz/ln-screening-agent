import io
import unittest
from zipfile import ZipFile,ZIP_DEFLATED
from ln_agent.document_intelligence import DocumentIntelligence,parse_document,DocumentTooLarge,UnsupportedDocument
from ln_agent.document_intelligence.locator import relevant_block_positions
from ln_agent.document_tools import DocumentFixtureResearchTool
from ln_agent import Case,Policy,Orchestrator
from ln_agent.models import Fact,Hit,Subject
from ln_agent.evidence import evaluate
from ln_agent.policy_guard import PolicyGuard,PolicyViolation
from ln_agent.skills import get_skill

SOURCE=("第一章 调查范围\n"
        "张宏于1998年担任某银行副行长。\n"
        "该银行于2023年发布本次公告。\n"
        "第二章 其他人员\n"
        "本案还出现另一名同名人员张宏，职务未载明。\n"
        "第三章 更正说明\n"
        "更正：部分原名单中人员出生日期有误，详见附件。\n").encode()

def document():
    return parse_document(SOURCE,document_id="bulletin",content_type="text/plain",
        source_url="https://example.invalid/synthetic-bulletin",title="模拟处罚通报",
        publisher="测试监管机构",document_number="SYN-TEST-001",
        retrieved_at="2026-11-11T00:00:00+00:00")

def fact(side,field,value,eid,origin="ln_structured",checked=True,context=""):
    return Fact.from_dict(dict(side=side,field=field,value=value,evidence_id=eid,origin=origin,checked=checked,context=context))

class TestDocumentIntelligence(unittest.TestCase):
    def test_exact_person_multiple_occurrences(self):
        doc=document();p=DocumentIntelligence().analyze(doc,["张宏"])
        self.assertEqual(p.coverage["target_matches"],2)
        self.assertNotEqual(p.targeted_spans[0].section,p.targeted_spans[1].section)
    def test_context_and_provenance_are_located(self):
        p=DocumentIntelligence().analyze(document(),["张宏"])
        span=p.targeted_spans[0]
        self.assertEqual(span.page,1)
        self.assertEqual(span.block_index,1)
        self.assertEqual(span.section,"第一章 调查范围")
        self.assertEqual(span.document_number,"SYN-TEST-001")
        self.assertEqual(span.exact_excerpt,"张宏于1998年担任某银行副行长。")
        self.assertEqual(len(span.sha256),64)
    def test_retraction_found_even_outside_target_paragraph(self):
        p=DocumentIntelligence().analyze(document(),["张宏"])
        self.assertTrue(any(l.label=="CORRECTION_OR_RETRACTION" for l in p.material_leads))
    def test_extracted_event_is_unchecked_and_cannot_exclude(self):
        p=DocumentIntelligence().analyze(document(),["张宏"])
        c=p.extracted_fact_candidates[0]
        self.assertEqual(c["value"],"1998")
        self.assertFalse(c["checked"])
        a=[fact("applicant","dob","2002-01-01","a",origin="kyb_verified")]
        h=[fact("hit",c["field"],c["value"],c["evidence_id"],origin=c["origin"],checked=c["checked"],context=c["context"])]
        self.assertFalse(evaluate(a,h,"person").exclusion_rules)
    def test_publication_year_plus_renzhi_word_not_extracted(self):
        content="张宏于1998年担任副行长。该单位于2023年发布了通报。2023年并非任职年份。".encode()
        d=parse_document(content,document_id="mixed",content_type="text/plain")
        c=DocumentIntelligence().analyze(d,["张宏"]).extracted_fact_candidates
        self.assertEqual([x["value"] for x in c],["1998"])

    def test_attached_resources_are_discovered_but_never_fetched(self):
        html=b'<h3>Notice</h3><p>Details in <a href="/files/appendix.xlsx">Appendix</a>.</p><a href="javascript:alert(1)">unsafe</a>'
        d=parse_document(html,document_id="links",content_type="text/html")
        packet=DocumentIntelligence().analyze(d,["Appendix"])
        self.assertEqual(len(packet.referenced_resources),1)
        self.assertEqual(packet.referenced_resources[0]["href"],"/files/appendix.xlsx")
        self.assertEqual(packet.referenced_resources[0]["status"],"not_fetched_not_verified")

    def test_publication_year_not_extracted_as_action(self):
        p=DocumentIntelligence().analyze(document(),["公告"])
        self.assertFalse(any(c["value"]=="2023" for c in p.extracted_fact_candidates))
    def test_no_target_still_scans_material(self):
        p=DocumentIntelligence().analyze(document(),["不存在的人名"])
        self.assertEqual(len(p.targeted_spans),0)
        self.assertGreater(len(p.material_leads),0)
    def test_citation_is_deterministic(self):
        d=document()
        a=DocumentIntelligence().analyze(d,["张宏"]).targeted_spans[0]
        b=DocumentIntelligence().analyze(d,["张宏"]).targeted_spans[0]
        self.assertEqual(a.evidence_id,b.evidence_id)
    def test_html_does_not_include_scripts(self):
        html=b'<h2>Penalty list</h2><p>John Doe served as Director.</p><script>John Doe hidden injected</script><table><tr><td>John Doe</td><td>2021</td></tr></table>'
        d=parse_document(html,document_id="html",content_type="text/html")
        self.assertFalse(any('hidden injected' in x.text for x in d.blocks))
        self.assertTrue(any(x.kind=="table_row" for x in d.blocks))
        self.assertEqual(len(relevant_block_positions(d,["John Doe"])),2)
    def test_heading_stops_context_at_new_section(self):
        d=document();s=DocumentIntelligence(context_window=3).analyze(d,["副行长"]).targeted_spans[0]
        self.assertFalse(any("另一名" in x for x in s.context_after))
    def test_latin_short_token_boundary(self):
        d=parse_document(b"Ann arrived\nAnna arrived",document_id="x",content_type="text/plain")
        self.assertEqual(len(relevant_block_positions(d,["Ann"])),1)
    def test_document_too_large_rejected(self):
        with self.assertRaises(DocumentTooLarge):parse_document(b"x"*(10*1024*1024+1),document_id="big",content_type="text/plain")
    def test_bad_content_type_rejected(self):
        with self.assertRaises(UnsupportedDocument):parse_document(b"x",document_id="bad",content_type="application/x-msdownload")
    def test_pdf_without_searchable_text_ocr_warning(self):
        from pypdf import PdfWriter
        writer=PdfWriter();writer.add_blank_page(width=300,height=300)
        buf=io.BytesIO();writer.write(buf)
        d=parse_document(buf.getvalue(),document_id="scan",content_type="application/pdf")
        self.assertEqual(len(d.blocks),0)
        self.assertTrue(any("OCR_MAY_BE_REQUIRED" in w for w in d.warnings))
    def test_docx_paragraph_table_preserves_order(self):
        xml='''<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
        <w:p><w:r><w:t>甲某</w:t></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>甲某</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>董事</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        <w:p><w:r><w:t>末尾</w:t></w:r></w:p></w:body></w:document>'''
        mem=io.BytesIO()
        with ZipFile(mem,"w",compression=ZIP_DEFLATED) as z:z.writestr("word/document.xml",xml)
        d=parse_document(mem.getvalue(),document_id="docx",content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertEqual([b.kind for b in d.blocks],["paragraph","table_row","paragraph"])
        self.assertEqual(d.blocks[1].text,"甲某 | 董事")
    def test_xlsx_row_location(self):
        from openpyxl import Workbook
        wb=Workbook();wb.active.title="人员名单";wb.active.append(["姓名","单位"]);wb.active.append(["张宏","某银行"])
        buf=io.BytesIO();wb.save(buf)
        d=parse_document(buf.getvalue(),document_id="xlsx",content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        spans=DocumentIntelligence().analyze(d,["张宏"]).targeted_spans
        self.assertEqual(len(spans),1)
        self.assertIn("row:2",spans[0].location_hint)
    def test_shared_parsed_doc_independent_hit_findings(self):
        docs={"b":{"data":SOURCE,"content_type":"text/plain","source_url":"https://example.invalid/syn"}}
        tool=DocumentFixtureResearchTool(docs)
        a=tool.query_document("doc:b",["张宏"])
        b=tool.query_document("doc:b",["另一名"])
        self.assertEqual(tool.read_count,1)
        self.assertNotEqual(a.document_packets[0]["coverage"]["target_matches"],0)
        self.assertEqual(b.document_packets[0]["coverage"]["target_matches"],1)
    def test_case_router_reads_document_packet_and_retains_review(self):
        person=Subject(subject_id="p",entity_type="person",role="董事",facts=[
            fact("applicant","name","张宏","kyb:name",origin="kyb_verified"),
            fact("applicant","dob","2002-01-01","kyb:dob",origin="kyb_verified")])
        hit=Hit(hit_id="h",subject_id="p",category="enforcement",facts=[fact("hit","name","张宏","ln:name")],research_keys=["doc:b"])
        tool=DocumentFixtureResearchTool({"b":{"data":SOURCE,"content_type":"text/plain","source_url":"https://example.invalid/syn"}})
        result=Orchestrator(Policy(),tool).run(Case(case_id="case",subjects=[person],hits=[hit]))["results"][0]
        self.assertEqual(result["route"],"FACT_VERIFICATION_REVIEW")
        self.assertEqual(result["actions"],["RESEARCH_QUERY:doc:b"])
        self.assertTrue(result["document_evidence"])
        self.assertTrue(result["document_evidence"][0]["extracted_fact_candidates"])
        self.assertEqual(result["investigation_status"],"awaiting_verification")
    def test_full_document_number_difference_does_not_exclude(self):
        a=[fact("applicant","document_number","DOC-A","a",origin="kyb_verified",context="CN_NATIONAL_ID")]
        h=[fact("hit","document_number","DOC-B","h",context="CN_NATIONAL_ID")]
        r=evaluate(a,h,"person")
        self.assertFalse(r.exclusion_rules)
        self.assertIn("DOCUMENT_DIFFERENCE_NEEDS_HISTORY_VERIFICATION",r.data_issues)
    def test_sanctions_dob_conflict_preserves_gate(self):
        subject=Subject("p","person","董事",[fact("applicant","dob","2002-01-01","kyb:a",origin="kyb_verified")])
        hit=Hit("s","p","sanctions",facts=[fact("hit","dob","1970-01-01","ln:s")])
        result=Orchestrator(Policy(),DocumentFixtureResearchTool({})).run(Case("c",[subject],[hit]))["results"][0]
        self.assertEqual(result["route"],"EXCLUSION_CANDIDATE")
        self.assertIn("SCREENING_REVIEW_REQUIRED",result["disposition_flags"])
        self.assertFalse(result["exclusion_authorized"])
    def test_sanctions_id_difference_preserves_gate(self):
        subject=Subject("p","person","董事",[fact("applicant","document_number","DOC-A","kyb:a",origin="kyb_verified",context="CN_NATIONAL_ID")])
        hit=Hit("s","p","sanctions",facts=[fact("hit","document_number","DOC-B","ln:s",context="CN_NATIONAL_ID")])
        result=Orchestrator(Policy(),DocumentFixtureResearchTool({})).run(Case("c",[subject],[hit]))["results"][0]
        self.assertEqual(result["route"],"EVIDENCE_CONFLICT_REVIEW")
        self.assertIn("SCREENING_REVIEW_REQUIRED",result["disposition_flags"])
    def test_unresolved_name_only_has_no_precision_score(self):
        subject=Subject("p","person","董事",[fact("applicant","name","张宏","kyb:n",origin="kyb_verified")])
        hit=Hit("s","p","enforcement",facts=[fact("hit","name","张宏","ln:s")])
        result=Orchestrator(Policy(),DocumentFixtureResearchTool({})).run(Case("c",[subject],[hit]))["results"][0]
        self.assertIsNone(result["suspicion"]["score"])
        self.assertEqual(result["skip_reason"],"NO_RESEARCH_KEYS")
        self.assertFalse(result["suspicion"]["evidence_sufficiency"]["sufficient_for_numeric_score"])
    def test_former_pep_negative_not_clamped(self):
        subject=Subject("p","person","董事",[fact("applicant","name","张宏","kyb:n",origin="kyb_verified"),
           fact("applicant","region","北京","kyb:r",origin="kyb_verified")])
        hit=Hit("s","p","pep",facts=[fact("hit","name","张宏","ln:n"),fact("hit","region","北京","ln:r"),fact("hit","pep_status","former","ln:p")])
        result=Orchestrator(Policy(),DocumentFixtureResearchTool({})).run(Case("c",[subject],[hit]))["results"][0]
        self.assertEqual(result["suspicion"]["score"],2)
        self.assertEqual(result["suspicion"]["negative_factors"],{"former_pep":-1})
    def test_skill_whitelist_is_runtime_guard(self):
        guard=PolicyGuard(Policy());s=get_skill("person")
        with self.assertRaises(PolicyViolation):guard.validate_action("unapproved:site",s,0)
    def test_model_fact_self_approval_rejected(self):
        guard=PolicyGuard(Policy());s=get_skill("person")
        fake=fact("hit","dob","1970-01-01","model:1",origin="model_extracted",checked=True)
        with self.assertRaises(PolicyViolation):guard.validate_facts([fake],s)
    def test_gate_compliance_policy_config(self):
        from dataclasses import replace
        subject=Subject("p","person","董事",[fact("applicant","dob","2002-01-01","kyb:a",origin="kyb_verified")])
        hit=Hit("s","p","sanctions",facts=[fact("hit","dob","1970-01-01","ln:s")])
        policy=replace(Policy(),mandatory_compliance_categories=frozenset({"sanctions"}))
        result=Orchestrator(policy,DocumentFixtureResearchTool({})).run(Case("c",[subject],[hit]))["results"][0]
        self.assertIn("COMPLIANCE_ESCALATION_REQUIRED",result["disposition_flags"])
        self.assertEqual(result["route"],"EXCLUSION_CANDIDATE")

if __name__=='__main__':unittest.main()
