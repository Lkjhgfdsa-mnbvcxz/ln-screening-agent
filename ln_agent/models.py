"""LN screening domain types. No network, no GUI side effects."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

# Do not treat these labels as proof that the underlying record is authentic.
ORIGINS = {"kyb_verified", "ln_structured", "official_primary", "public_secondary", "model_extracted", "reviewer_verified"}

@dataclass(frozen=True)
class Fact:
    side: str                 # applicant | hit
    field: str                # name, dob, document_number, region, etc.
    value: str
    evidence_id: str          # stable source anchor / uploaded document ID
    origin: str               # origin classification, NOT a confidence score
    checked: bool = False    # checked by an authorized source adapter or human
    context: str = ""        # e.g. CN_NATIONAL_ID, held_position
    source_url: str = ""     # optional; never automatically fetched by core
    verification_id: str = ""  # accepted only when matched to the trusted verifier ledger
    extraction_verified: bool | None = None  # False always disqualifies hard evidence
    content_verified: bool | None = None     # False always disqualifies hard evidence
    date_precision: str = ""                 # e.g. year versus full calendar date

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Fact":
        obj = cls(**raw)
        if obj.side not in ("applicant", "hit"):
            raise ValueError(f"bad fact side: {obj.side}")
        if obj.origin not in ORIGINS:
            raise ValueError(f"unknown origin: {obj.origin}")
        if not obj.evidence_id or not str(obj.value).strip():
            raise ValueError("fact requires a value and evidence_id")
        return obj

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Hit:
    hit_id: str
    subject_id: str
    category: str             # sanctions | pep | enforcement | adverse_media | other
    entity_type: str = "person" # person | company | address
    facts: list[Fact] = field(default_factory=list)
    research_keys: list[str] = field(default_factory=list)
    alert_id: str = ""
    notes: str = ""
    risk_event: dict[str, Any] = field(default_factory=dict)  # source-attributed event, not assumed verified
    screening_url: str = ""  # display-only; never fetched

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Hit":
        return cls(hit_id=raw["hit_id"], subject_id=raw["subject_id"], category=raw.get("category", "other"),
                   entity_type=raw.get("entity_type", "person"),
                   facts=[Fact.from_dict(x) for x in raw.get("facts", [])],
                   research_keys=list(raw.get("research_keys", [])),
                   alert_id=raw.get("alert_id", ""), notes=raw.get("notes", ""),
                   risk_event=dict(raw.get("risk_event") or {}), screening_url=raw.get("screening_url", ""))

@dataclass
class Subject:
    subject_id: str
    entity_type: str
    role: str
    facts: list[Fact]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Subject":
        return cls(subject_id=raw["subject_id"], entity_type=raw["entity_type"],
                   role=raw.get("role", ""), facts=[Fact.from_dict(x) for x in raw.get("facts", [])])

@dataclass
class Case:
    case_id: str
    subjects: list[Subject]
    hits: list[Hit]
    context: dict[str, Any] = field(default_factory=dict)
    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Case":
        subjects = [Subject.from_dict(x) for x in raw.get("subjects", [])]
        hits = [Hit.from_dict(x) for x in raw.get("hits", [])]
        subject_ids = {s.subject_id for s in subjects}
        if len(subject_ids) != len(subjects):
            raise ValueError("duplicate subject_id")
        for hit in hits:
            if hit.subject_id not in subject_ids:
                raise ValueError(f"hit {hit.hit_id}: unknown subject_id {hit.subject_id}")
            matching = next(s for s in subjects if s.subject_id == hit.subject_id)
            if hit.entity_type != matching.entity_type:
                raise ValueError(f"hit {hit.hit_id}: entity type mismatch")
        if len({h.hit_id for h in hits}) != len(hits):
            raise ValueError("duplicate hit_id")
        return cls(case_id=raw["case_id"], subjects=subjects, hits=hits, context=dict(raw.get("context") or {}))

@dataclass
class EvidenceResult:
    exclusion_rules: list[str] = field(default_factory=list)
    linked_rules: list[str] = field(default_factory=list)
    soft_signals: list[str] = field(default_factory=list)
    data_issues: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)

@dataclass
class Decision:
    hit_id: str
    route: str
    identity: str             # excluded_candidate | strong_link | unresolved | conflict
    suspicion: dict[str, Any] | None
    evidence: dict[str, Any]
    reasons: list[str]
    actions: list[str]
    history: list[dict[str, Any]]
    review_required: bool = True   # legacy formal disposition authorization; not a manual research queue
    policy_version: str = ""
    disposition_flags: list[str] = field(default_factory=list)
    exclusion_evidence_detected: bool = False
    exclusion_authorized: bool = False
    investigation_status: str = "not_exhausted"
    skip_reason: str | None = None
    tried_actions: list[dict[str, Any]] = field(default_factory=list)
    evidence_of_attempt: list[dict[str, Any]] = field(default_factory=list)
    document_evidence: list[dict[str, Any]] = field(default_factory=list)
    hit_evidence_links: list[dict[str, Any]] = field(default_factory=list)
    verification_records: list[dict[str, Any]] = field(default_factory=list)
    # Full provenance of facts acquired during bounded research (source tool,
    # action key, origin, checked state, evidence_id, source_url). Read-only.
    research_facts: list[dict[str, Any]] = field(default_factory=list)
    corroboration: list[dict[str, Any]] = field(default_factory=list)
    # Integration additions: computed from actual runtime decisions, never from README text.
    rule_findings: list[dict[str, Any]] = field(default_factory=list)
    gate: dict[str, Any] = field(default_factory=dict)
    gate_final_check: dict[str, Any] = field(default_factory=dict)
    explanation: dict[str, Any] = field(default_factory=dict)
    execution_path: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    disposition: dict[str, Any] = field(default_factory=dict)
    version_snapshot: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
