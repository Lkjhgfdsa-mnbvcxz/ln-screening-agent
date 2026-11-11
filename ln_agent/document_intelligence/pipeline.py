"""Document Intelligence pipeline: locate -> read context -> sweep -> cited candidates."""
from __future__ import annotations
import re
from hashlib import sha256
from .models import SourceDocument, EvidencePacket
from .locator import relevant_block_positions
from .context_reader import citation_span
from .material_sweep import scan_material

# Strict small Chinese event patterns: date must be coupled to an action in the same quote.
_EVENT_PATTERN = re.compile(
    r"(?P<year>(?:19|20)\d{2})年(?:\d{1,2}月)?[^。！？；;\n]{0,18}?"
    r"(?P<verb>担任|任职(?!年份)|出任|就任|当选|实施|参与)"
)
_NON_EVENT_CONTEXT = re.compile(r"发布|公告|报道|刊登|更正|撤销|否认|并非|误写|录入错误|澄清")

class DocumentIntelligence:
    def __init__(self, *, max_target_spans: int=30, max_material_leads:int=16, context_window:int=1):
        self.max_target_spans=max_target_spans
        self.max_material_leads=max_material_leads
        self.context_window=context_window

    def analyze(self, doc: SourceDocument, queries: list[str], *, side: str="hit") -> EvidencePacket:
        if side not in {"hit","applicant"}: raise ValueError("side must be hit or applicant")
        matches=relevant_block_positions(doc,queries,self.max_target_spans)
        spans=[citation_span(doc,i,q,self.context_window) for i,q in matches]
        lead_items,lead_spans=scan_material(doc,{i for i,_ in matches},self.max_material_leads)
        # Cited extractions are candidate facts only. They must be checked independently.
        candidates=[];seen=set()
        for s in spans:
            text=s.exact_excerpt
            # A single paragraph can describe a publication year, a current role,
            # and two different people. Never join unrelated sentences to infer an event.
            for sentence in re.split(r"[。！？；;\n]",text):
                if not sentence.strip() or _NON_EVENT_CONTEXT.search(sentence): continue
                if s.query.casefold() not in sentence.casefold(): continue
                for m in _EVENT_PATTERN.finditer(sentence):
                    year=m.group("year")
                    signature=(s.evidence_id,year)
                    if signature in seen:continue
                    seen.add(signature)
                    candidate_id="FC-"+sha256((doc.sha256+"|"+s.evidence_id+"|"+year+"|"+sentence.strip()).encode()).hexdigest()[:20]
                    candidates.append({
                      "candidate_id":candidate_id,
                      "side":side,"field":"acted_in_year","value":year,
                      "evidence_id":s.evidence_id,"origin":"model_extracted",
                      "checked":False,"context":"event_candidate_unattributed",
                      "source_url":doc.source_url,
                      "evidence_quote":sentence.strip(),
                      "location":{"page":s.page,"block_index":s.block_index},
                    })
        allspans=[];seen_ids=set()
        for s in spans+lead_spans:
            if s.evidence_id not in seen_ids:
                allspans.append(s);seen_ids.add(s.evidence_id)
        return EvidencePacket(document_id=doc.document_id,source_url=doc.source_url,sha256=doc.sha256,
           targeted_spans=spans,material_leads=lead_items,evidence_spans=allspans,
           extracted_fact_candidates=candidates,parse_warnings=list(doc.warnings),
           referenced_resources=[dict(x) for x in doc.references],
           coverage={"blocks_scanned":len(doc.blocks),"target_matches":len(spans),
                     "material_leads":len(lead_items),"full_text_read":True,
                     "ocr_performed":False,"source_identity_verified":False,
                     "source_metadata_verified":False,"references_found":len(doc.references),
                     "truncated_target_results":len(spans)>=self.max_target_spans,
                     "truncated_material_results":len(lead_items)>=self.max_material_leads})
