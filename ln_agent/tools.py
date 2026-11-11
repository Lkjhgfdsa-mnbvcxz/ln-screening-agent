"""Tool boundary. Offline fixture only; no LN, web or QCC access here."""
from __future__ import annotations
from threading import Lock
from .models import Fact
from .document_tools import ResearchOutcome

class FixtureResearchTool:
    """A replaceable, read-only source adapter with a shared concurrent cache."""
    def __init__(self, fixture: dict[str, list[dict]] | None = None):
        self.fixture = fixture or {}
        self.cache: dict[str, list[Fact]] = {}
        self.lock = Lock()
        self.read_count = 0

    def query(self, key: str) -> list[Fact]:
        with self.lock:
            if key not in self.cache:
                self.cache[key] = [Fact.from_dict(x) for x in self.fixture.get(key, [])]
                self.read_count += 1
            return list(self.cache[key])

class InvestigationAgent:
    """Bounded sub-agent. Tools allowlist + explicit questions, no arbitrary actions."""
    def __init__(self, tool: FixtureResearchTool):
        self.tool = tool

    def investigate(self, key: str) -> list[Fact]:
        return self.investigate_with_evidence(key,[]).facts

    def investigate_with_evidence(self,key:str,queries:list[str])->ResearchOutcome:
        # The adapter is read-only. It can suggest unverified extracted fact candidates.
        if hasattr(self.tool,"query_document"):
            outcome=self.tool.query_document(key,queries)
            return ResearchOutcome(facts=[f for f in outcome.facts if f.side=="hit"],
                                   document_packets=outcome.document_packets)
        return ResearchOutcome(facts=[f for f in self.tool.query(key) if f.side=="hit"])
