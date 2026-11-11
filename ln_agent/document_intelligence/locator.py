"""High-recall exact/normalized local retrieval; no guessy fuzzy same-person matching."""
from __future__ import annotations
import re
import unicodedata
from .models import SourceDocument

def canonical(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC",s).casefold()
                   if ch.isalnum())

def relevant_block_positions(doc: SourceDocument, queries: list[str], limit: int = 35) -> list[tuple[int,str]]:
    """Returns (block index, matching query). Chinese exact substrings; ASCII token boundaries."""
    found=[]; seen=set()
    cleaned=[q.strip() for q in queries if q and len(canonical(q))>=2]
    for b in doc.blocks:
        src=canonical(b.text)
        for q in cleaned:
            token=canonical(q)
            if token not in src: continue
            # Prevent short English aliases from matching a longer single word.
            if q.isascii() and len(token)<5 and re.search(r"\b"+re.escape(q.casefold())+r"\b",b.text.casefold()) is None:
                continue
            signature=(b.index,q.casefold())
            if signature in seen:continue
            seen.add(signature);found.append((b.index,q))
            if len(found)>=limit:return found
    return found
