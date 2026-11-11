"""Read-only local document intelligence; NEVER fetch untrusted URLs automatically."""
from .pipeline import DocumentIntelligence, EvidencePacket
from .parsers import parse_document, UnsupportedDocument, DocumentTooLarge

__all__ = ["DocumentIntelligence", "EvidencePacket", "parse_document", "UnsupportedDocument", "DocumentTooLarge"]
