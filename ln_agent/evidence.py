"""Deterministic comparisons. Model-extracted text never alone triggers hard findings."""
from __future__ import annotations
import re
import unicodedata
from datetime import date
from collections import defaultdict
from .models import Fact, EvidenceResult

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    return re.sub(r"[\s.,，。\-_/（）()]+", "", s)

def iso_dob(raw: str) -> date | None:
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError:
        return None

def eligible_for_hard(f: Fact, accepted_verifications: frozenset[str] = frozenset()) -> bool:
    # Extraction correctness and source content accuracy are independent questions.
    # A verified-looking source with explicitly failed extraction/content cannot be hard evidence.
    if f.extraction_verified is False or f.content_verified is False:
        return False
    if f.origin == "reviewer_verified":
        return bool(f.checked and f.verification_id and f.verification_id in accepted_verifications)
    return f.checked and f.origin in {"kyb_verified", "ln_structured", "official_primary"}

def by_field(fs: list[Fact]) -> dict[str, list[Fact]]:
    d: dict[str, list[Fact]] = defaultdict(list)
    for f in fs:
        d[f.field].append(f)
    return d

def compatible_pair(a: Fact, b: Fact, accepted_verifications: frozenset[str] = frozenset()) -> bool:
    return eligible_for_hard(a, accepted_verifications) and eligible_for_hard(b, accepted_verifications)

def evaluate(applicant: list[Fact], hits: list[Fact], entity_type: str,
             accepted_verifications: frozenset[str] = frozenset()) -> EvidenceResult:
    r = EvidenceResult()
    a = by_field(applicant); h = by_field(hits)
    def mark(rule: str, left: Fact, right: Fact, exclusion: bool):
        (r.exclusion_rules if exclusion else r.linked_rules).append(rule)
        r.anchors.extend([left.evidence_id, right.evidence_id])

    # Unknown or mixed-subject evidence must not be coerced into a hard result.
    for side, d in (("applicant", a), ("hit", h)):
        for f in ("dob", "document_number", "registration_number"):
            vals = {norm(x.value) for x in d.get(f, []) if eligible_for_hard(x, accepted_verifications)}
            if len(vals) > 1:
                r.data_issues.append(f"INTERNAL_CONFLICT:{side}:{f}")

    for x in a.get("name", []) + a.get("company_name", []):
        for y in h.get(x.field, []):
            if norm(x.value) == norm(y.value):
                r.soft_signals.append("name_exact")
                break
    for field in ("region", "business_region"):
        for x in a.get(field, []):
            if any(norm(x.value) == norm(y.value) for y in h.get("region", [])):
                r.soft_signals.append("region_overlap")
                break
    for x in a.get("address", []) + a.get("business_address", []):
        if any(norm(x.value) == norm(y.value) for y in h.get("address", [])):
            r.soft_signals.append("address_overlap")
            break
    for x in a.get("company_name", []):
        if any(norm(x.value) == norm(y.value) for y in h.get("employer", [])):
            r.soft_signals.append("company_link")
            break

    for x in a.get("dob", []):
        for y in h.get("dob", []):
            ad, hd = iso_dob(x.value), iso_dob(y.value)
            if not (ad and hd and compatible_pair(x, y, accepted_verifications)):
                continue
            if ad == hd:
                mark("DOB_EXACT_MATCH", x, y, False)
                r.soft_signals.append("dob_exact")
            else:
                mark("DOB_EXACT_CONFLICT", x, y, True)

    # A time impossibility requires an explicit time of a person's *action*.
    # Publication, conviction reporting and source update years do NOT qualify.
    if entity_type == "person":
        for x in a.get("dob", []):
            ad = iso_dob(x.value)
            if ad is None or not eligible_for_hard(x, accepted_verifications):
                continue
            for y in h.get("acted_in_year", []):
                if not eligible_for_hard(y, accepted_verifications) or y.context not in {"held_position", "committed_act", "participated_event"}:
                    continue
                try: year = int(y.value)
                except ValueError: continue
                if year < ad.year:
                    mark("PRE_BIRTH_ACTION_IMPOSSIBLE", x, y, True)

    # Document matches are strong only within the same document namespace.
    for field, namespace in (("document_number", "CN_NATIONAL_ID"), ("registration_number", "COMPANY_REGISTRY")):
        if field == "registration_number" and entity_type != "company":
            continue
        if field == "document_number" and entity_type != "person":
            continue
        for x in a.get(field, []):
            for y in h.get(field, []):
                if not (compatible_pair(x, y, accepted_verifications) and x.context == y.context and x.context):
                    continue
                # Masked values are not identity-level equality or conflicts.
                if any(ch in x.value + y.value for ch in "*xX•"):
                    continue
                if norm(x.value) == norm(y.value):
                    mark("DOCUMENT_EXACT_MATCH" if field == "document_number" else "COMPANY_REGISTRATION_MATCH", x, y, False)
                elif x.context == namespace:
                    # Full ID mismatch is a verification lead, not an automatic exclusion.
                    # Multiple documents / historic replacements / source errors exist.
                    r.soft_signals.append("document_difference_verify_history")
                    r.data_issues.append("DOCUMENT_DIFFERENCE_NEEDS_HISTORY_VERIFICATION")
                    r.anchors.extend([x.evidence_id,y.evidence_id])

    # A photograph mismatch or geographic difference is insufficient for automated exclusion.
    for x in h.get("photo_comparison", []):
        if norm(x.value) == "different":
            r.soft_signals.append("photo_difference_human_only")
    if any(norm(x.value) == "former" for x in h.get("pep_status", [])):
        r.soft_signals.append("former_pep")
    if any(norm(x.value) == "current" for x in h.get("pep_status", [])):
        r.soft_signals.append("ongoing_pep")
    if any(norm(x.value) == "recent" for x in h.get("event_recency", [])):
        r.soft_signals.append("recent_adverse_event")
    return r
