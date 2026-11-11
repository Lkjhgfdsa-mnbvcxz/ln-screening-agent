"""A local, read-only document research adapter for the Investigation sub-agent.

Only bytes provided by a trusted caller are accepted. URLs are provenance labels,
not retrieval instructions. Parsed source bytes are shared; per-hit findings are not.
"""
from __future__ import annotations
from dataclasses import dataclass,field
from threading import Lock
from .models import Fact
from .document_intelligence import DocumentIntelligence, parse_document

@dataclass
class ResearchOutcome:
    facts: list[Fact]=field(default_factory=list)
    document_packets: list[dict]=field(default_factory=list)

class DocumentFixtureResearchTool:
    def __init__(self, documents:dict[str,dict], *, extra_fact_fixtures:dict|None=None):
        # documents: {document_id:{data:bytes,content_type,...}}; never network.
        self.documents=documents
        self.extra_fact_fixtures=extra_fact_fixtures or {}
        self.cache={};self.lock=Lock();self.read_count=0
        self.engine=DocumentIntelligence()

    def get_parsed_document(self,doc_id:str):
        # Only already-parsed approved fixture documents; no new I/O or fetch.
        with self.lock:
            return self.cache.get(doc_id)

    def query(self,key:str)->list[Fact]:
        # Compatible with the old tool protocol.
        return [Fact.from_dict(f) for f in self.extra_fact_fixtures.get(key,[])]

    def query_document(self,key:str,queries:list[str])->ResearchOutcome:
        if not key.startswith("doc:"):
            return ResearchOutcome(facts=self.query(key))
        docid=key[4:]
        if docid not in self.documents: raise KeyError(f"unknown allowed document id: {docid}")
        with self.lock:
            if docid not in self.cache:
                record=self.documents[docid]
                parsed=parse_document(record["data"],document_id=docid,
                  content_type=record["content_type"],source_url=record.get("source_url",""),
                  title=record.get("title",""),publisher=record.get("publisher",""),
                  document_number=record.get("document_number",""),
                  retrieved_at=record.get("retrieved_at",""))
                self.cache[docid]=parsed;self.read_count+=1
            doc=self.cache[docid]
        packet=self.engine.analyze(doc,queries)
        safe_facts=[]
        for c in packet.extracted_fact_candidates:
            safe_facts.append(Fact.from_dict({k:c[k] for k in
               ("side","field","value","evidence_id","origin","checked","context","source_url")}))
        return ResearchOutcome(facts=safe_facts,document_packets=[packet.to_dict()])
