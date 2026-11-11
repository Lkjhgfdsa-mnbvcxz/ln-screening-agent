"""Evidence location and document provenance domain models."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass(frozen=True)
class Block:
    index: int
    page: int | None
    text: str
    section: str = ""
    kind: str = "paragraph"
    location_hint: str = ""

@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    source_url: str
    title: str
    publisher: str
    content_type: str
    sha256: str
    blocks: tuple[Block, ...]
    warnings: tuple[str, ...] = ()
    retrieved_at: str = ""
    document_number: str = ""
    references: tuple[dict[str, str], ...] = ()

@dataclass(frozen=True)
class EvidenceSpan:
    evidence_id: str
    document_id: str
    source_url: str
    sha256: str
    title: str
    publisher: str
    query: str
    page: int | None
    block_index: int
    section: str
    location_hint: str
    exact_excerpt: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]
    retrieved_at: str
    document_number: str
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class MaterialLead:
    label: str
    evidence_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class EvidencePacket:
    document_id: str
    source_url: str
    sha256: str
    targeted_spans: list[EvidenceSpan] = field(default_factory=list)
    material_leads: list[MaterialLead] = field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = field(default_factory=list)
    extracted_fact_candidates: list[dict[str, Any]] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    referenced_resources: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_url": self.source_url,
            "sha256": self.sha256,
            "targeted_spans": [s.to_dict() for s in self.targeted_spans],
            "material_leads": [s.to_dict() for s in self.material_leads],
            "evidence_spans": [s.to_dict() for s in self.evidence_spans],
            "extracted_fact_candidates": self.extracted_fact_candidates,
            "parse_warnings": self.parse_warnings,
            "coverage": self.coverage,
            "referenced_resources": self.referenced_resources,
        }
