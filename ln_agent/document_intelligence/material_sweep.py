"""Bounded whole-document alerts for amendments, identity identifiers, dates and related entities.
They are leads, not automatic identity evidence or confirmed substantive facts.
"""
from __future__ import annotations
import re
from .models import SourceDocument,MaterialLead
from .context_reader import citation_span

PATTERNS={
    "IDENTITY_FIELD":re.compile(r"(身份证|证件号|出生日期|出生于|birth date|passport|registration no|统一社会信用代码)",re.I),
    "CORRECTION_OR_RETRACTION":re.compile(r"(更正|撤销|撤回|纠正|原文有误|amendment|corrected|withdrawn|revoked)",re.I),
    "TENURE_OR_STATUS":re.compile(r"(任职|离任|退休|原任|时任|曾任|appointed|resigned|former|retired)",re.I),
    "CASE_LINK":re.compile(r"(案号|处罚决定|关联企业|关联人员|附表|附件|case number|appendix)",re.I),
    "DATED_EVENT":re.compile(r"((?:19|20)\d{2}年|(?:19|20)\d{2}-\d{2}-\d{2})"),
}

def scan_material(doc: SourceDocument, exclude_indices: set[int], limit:int=18) -> tuple[list[MaterialLead],list]:
    leads=[];spans=[];seen=set()
    for b in doc.blocks:
        for label,pattern in PATTERNS.items():
            if not pattern.search(b.text):continue
            # Major retractions/corrections should be considered even at a distant location.
            if b.index in exclude_indices and label!="CORRECTION_OR_RETRACTION": continue
            if (b.index,label) in seen:continue
            seen.add((b.index,label))
            s=citation_span(doc,b.index,f"material:{label}",window=1)
            leads.append(MaterialLead(label=label,evidence_id=s.evidence_id,
                    reason="全篇材料扫描发现需核实的潜在重要信息，尚未确认与筛查主体关联"))
            spans.append(s)
            if len(leads)>=limit:return leads,spans
    return leads,spans
