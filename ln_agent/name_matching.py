"""Conservative, FIELD-SPECIFIC English company legal-form equivalence.

Only name comparisons use this function. Registry identifiers, personal names,
addresses and document numbers retain their independent normalization rules.
A normalized legal-form match is SOFT evidence and never proof of legal identity.
"""
from __future__ import annotations
import re
import unicodedata

LEGAL_SUFFIXES = {
    "ltd": "limited", "limited": "limited",
    "co": "company", "company": "company",
    "inc": "incorporated", "incorporated": "incorporated",
    "corp": "corporation", "corporation": "corporation",
}

def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return re.sub(r"[\s.,，。\-_/（）()]+", "", normalized)

def normalize_company_name(value: str) -> str:
    """Expand common legal suffixes only at TOKEN boundaries at the name's end.

    A bare suffix (e.g. 'LTD') is not treated as a useful legal-entity name.
    We deliberately do not remove legal forms or merge unrelated legal forms.
    """
    raw = unicodedata.normalize("NFKC", str(value)).casefold()
    tokens = re.findall(r"[^\W_]+", raw, flags=re.UNICODE)
    if len(tokens) < 2:
        return _plain(value)
    index = len(tokens) - 1
    while index >= 1 and tokens[index] in LEGAL_SUFFIXES:
        index -= 1
    suffix_start = index + 1
    canonical = tokens[:suffix_start] + [LEGAL_SUFFIXES[token] for token in tokens[suffix_start:]]
    return "".join(canonical)

def company_name_match_kind(left: str, right: str) -> str | None:
    """Return literal-normalized / legal-suffix-equivalent / not matched."""
    if not _plain(left) or not _plain(right):
        return None
    if _plain(left) == _plain(right):
        return "normalized_exact"
    if normalize_company_name(left) == normalize_company_name(right):
        return "legal_suffix_equivalent"
    return None
