"""Small, reproducible context windows with precise document location."""
from __future__ import annotations
from hashlib import sha256
from .models import EvidenceSpan,SourceDocument

def citation_span(doc: SourceDocument,block_index: int,query: str,window: int=1) -> EvidenceSpan:
    if window<0 or window>5: raise ValueError("window must be in [0,5]")
    b=doc.blocks[block_index]
    # An explicit heading starts a new section: avoid silently mixing distinct people.
    before=[];after=[]
    for i in range(max(0,block_index-window),block_index):
        item=doc.blocks[i]
        if item.section==b.section or item.kind=="heading":before.append(item.text)
    for i in range(block_index+1,min(len(doc.blocks),block_index+window+1)):
        item=doc.blocks[i]
        if item.kind=="heading" or (b.section and item.section!=b.section):break
        after.append(item.text)
    token=f"{doc.document_id}|{doc.sha256}|{block_index}|{query}"
    eid="EV-"+sha256(token.encode()).hexdigest()[:16]
    return EvidenceSpan(evidence_id=eid,document_id=doc.document_id,source_url=doc.source_url,
        sha256=doc.sha256,title=doc.title,publisher=doc.publisher,query=query,page=b.page,
        block_index=b.index,section=b.section,location_hint=b.location_hint,exact_excerpt=b.text,
        context_before=tuple(before),context_after=tuple(after),retrieved_at=doc.retrieved_at,
        document_number=doc.document_number)
