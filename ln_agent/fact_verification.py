"""V0.4: Evidence provenance and per-hit fact verification.

A citation can be located mechanically, but source authenticity, attribution to
one LN hit, interpretation, and source-content accuracy are independent gates.
No LLM output may satisfy the human/approved-verifier attestations in this demo.

Offline authorization is a test fixture, not production authentication.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Any
from .models import Fact
from .document_intelligence.models import SourceDocument
from .document_intelligence.context_reader import citation_span
from .document_intelligence.pipeline import _EVENT_PATTERN, _NON_EVENT_CONTEXT

VALID_EVENT_CONTEXTS = frozenset({"held_position", "committed_act", "participated_event"})


@dataclass(frozen=True)
class ReviewAttestation:
    case_id: str
    hit_id: str
    document_id: str
    source_sha256: str
    candidate_id: str
    reviewer_id: str
    event_context: str
    source_authenticated: bool
    person_attributed_to_hit: bool
    event_meaning_checked: bool
    source_content_checked: bool
    conflicting_material_reviewed: bool
    note: str = ""
    # V0.5: supplied by an authorized human reviewing the ORIGINAL origin and
    # event identity. Different URLs or publishers alone do not certify either.
    claim_id: str = ""
    source_origin_id: str = ""
    source_independence_checked: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ReviewAttestation":
        return cls(**raw)


@dataclass
class VerificationOutput:
    verified_facts: list[Fact]
    verification_records: list[dict[str, Any]]


class FactVerifier:
    """Trusted orchestrator-side verifier; never exposed as an agent tool.

    Only explicitly supplied human attestations from an allowlist may turn a
    model-extracted document candidate into a hard-eligible reviewer fact.
    """
    def __init__(self, *, attestations: list[ReviewAttestation] | None = None,
                 authorized_reviewers: frozenset[str] = frozenset()):
        self.authorized_reviewers = authorized_reviewers
        self.attestations: dict[tuple[str, str, str], ReviewAttestation] = {}
        for att in attestations or []:
            key = (att.case_id, att.hit_id, att.candidate_id)
            if key in self.attestations:
                raise ValueError("duplicate case/hit/candidate attestation")
            self.attestations[key] = att

    @staticmethod
    def _record(*, case_id: str, hit_id: str, candidate: dict, status: str,
                reasons: list[str], span: dict | None = None,
                verification_id: str | None = None, reviewer_id: str | None = None) -> dict:
        return {
            "case_id": case_id, "hit_id": hit_id,
            "candidate_id": candidate.get("candidate_id", ""),
            "evidence_id": candidate.get("evidence_id", ""),
            "status": status, "reasons": reasons,
            "document_location": {
                "page": (span or {}).get("page"),
                "block_index": (span or {}).get("block_index"),
                "location_hint": (span or {}).get("location_hint", ""),
                "section": (span or {}).get("section", ""),
            },
            "source_url": candidate.get("source_url", ""),
            "verification_id": verification_id,
            "reviewer_id": reviewer_id,
        }

    def verify_packet(self, *, case_id: str, hit_id: str,
                      document: SourceDocument | None,
                      packet: dict[str, Any]) -> VerificationOutput:
        records: list[dict] = []
        verified_facts: list[Fact] = []
        spans = {s["evidence_id"]: s for s in packet.get("evidence_spans", [])}
        correction_found = any(x.get("label") == "CORRECTION_OR_RETRACTION"
                               for x in packet.get("material_leads", []))
        for c in packet.get("extracted_fact_candidates", []):
            problems: list[str] = []
            span = spans.get(c.get("evidence_id", ""))
            if not document or document.sha256 != packet.get("sha256") or document.document_id != packet.get("document_id"):
                problems.append("SOURCE_SNAPSHOT_MISMATCH")
            if not span:
                problems.append("CITATION_NOT_FOUND")
            if document and span:
                idx = span.get("block_index")
                if not isinstance(idx, int) or idx < 0 or idx >= len(document.blocks):
                    problems.append("INVALID_DOCUMENT_LOCATION")
                else:
                    block = document.blocks[idx]
                    expected = citation_span(document, idx, span.get("query", ""))
                    if (expected.evidence_id != c.get("evidence_id") or
                        block.text != span.get("exact_excerpt") or
                        span.get("sha256") != document.sha256 or
                        span.get("document_id") != document.document_id or
                        span.get("source_url") != document.source_url or
                        c.get("source_url") != document.source_url or
                        span.get("page") != block.page or
                        c.get("location", {}).get("page") != block.page or
                        c.get("location", {}).get("block_index") != idx):
                        problems.append("PROVENANCE_LOCATION_MISMATCH")
                    quote = c.get("evidence_quote", "")
                    if not quote or quote not in block.text:
                        problems.append("QUOTE_NOT_AT_CITED_LOCATION")
                    year = str(c.get("value", ""))
                    if (c.get("field") != "acted_in_year" or
                        c.get("side") != "hit" or
                        not any(m.group("year") == year for m in _EVENT_PATTERN.finditer(quote)) or
                        _NON_EVENT_CONTEXT.search(quote)):
                        problems.append("UNSUPPORTED_OR_AMBIGUOUS_EVENT")
                    expected_id = "FC-" + sha256(
                        (document.sha256 + "|" + c.get("evidence_id", "") + "|" + year + "|" + quote).encode()
                    ).hexdigest()[:20]
                    if c.get("candidate_id") != expected_id:
                        problems.append("CANDIDATE_DIGEST_MISMATCH")
            if problems:
                records.append(self._record(case_id=case_id, hit_id=hit_id,
                    candidate=c, status="REJECTED_PROVENANCE", reasons=problems, span=span))
                continue
            att = self.attestations.get((case_id, hit_id, c["candidate_id"]))
            if att is None:
                records.append(self._record(case_id=case_id, hit_id=hit_id, candidate=c,
                    status="PENDING_HUMAN_VERIFICATION",
                    reasons=["SOURCE_AUTHENTICITY_ATTRIBUTION_AND_EVENT_UNVERIFIED"], span=span))
                continue
            failures=[]
            if att.reviewer_id not in self.authorized_reviewers:
                failures.append("UNAUTHORIZED_REVIEWER")
            if att.source_sha256 != document.sha256 or att.document_id != document.document_id:
                failures.append("ATTESTATION_SOURCE_MISMATCH")
            for flag, code in ((att.source_authenticated,"SOURCE_UNAUTHENTICATED"),
                               (att.person_attributed_to_hit,"HIT_ENTITY_NOT_ATTRIBUTED"),
                               (att.event_meaning_checked,"EVENT_MEANING_UNCONFIRMED"),
                               (att.source_content_checked,"SOURCE_CONTENT_NOT_ACCEPTED")):
                if not flag:failures.append(code)
            if correction_found and not att.conflicting_material_reviewed:
                failures.append("CORRECTION_OR_RETRACTION_UNRESOLVED")
            if att.event_context not in VALID_EVENT_CONTEXTS:
                failures.append("INVALID_ATTESTED_EVENT_CONTEXT")
            # Scanned/partially parsed sources require a separate manual coverage decision.
            if (packet.get("parse_warnings") or
                packet.get("coverage", {}).get("truncated_target_results") or
                packet.get("coverage", {}).get("truncated_material_results") or
                not packet.get("coverage", {}).get("full_text_read", False)):
                failures.append("INCOMPLETE_DOCUMENT_COVERAGE")
            if failures:
                records.append(self._record(case_id=case_id, hit_id=hit_id,
                    candidate=c, status="ATTESTATION_INCOMPLETE", reasons=failures,
                    span=span, reviewer_id=att.reviewer_id))
                continue
            token = "|".join((case_id, hit_id, document.sha256, c["candidate_id"], att.reviewer_id,
                               att.event_context, "verified_v0.4"))
            verification_id="VR-"+sha256(token.encode()).hexdigest()[:20]
            fact=Fact(side="hit", field=c["field"], value=str(c["value"]),
                      evidence_id=c["evidence_id"], origin="reviewer_verified",
                      checked=True, context=att.event_context, source_url=document.source_url,
                      verification_id=verification_id)
            verified_facts.append(fact)
            # Only a successful review may assert cross-source event and lineage
            # metadata; annotations on unreviewed packets are not trusted.
            review_record = self._record(case_id=case_id, hit_id=hit_id,
                candidate=c, status="VERIFIED_FOR_COMPARISON", reasons=["ALL_ATTESTATIONS_PASSED"],
                span=span, verification_id=verification_id, reviewer_id=att.reviewer_id)
            review_record.update({
                "field": c["field"], "value": str(c["value"]),
                "claim_id": att.claim_id,
                "source_origin_id": att.source_origin_id if att.source_independence_checked else "",
                "source_independence_checked": att.source_independence_checked,
                "source_sha256": document.sha256,
                "event_context": att.event_context,
            })
            records.append(review_record)
        return VerificationOutput(verified_facts=verified_facts, verification_records=records)
