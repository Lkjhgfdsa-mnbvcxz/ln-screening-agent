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
    """Bounded sub-agent. Tools allowlist + explicit questions, no arbitrary actions.

    `extra_tools` maps a REGISTERED tool name to its local adapter. The Router
    resolves the name from the source key and has already asked PolicyGuard to
    authorize it. Missing adapters fail closed (TOOL_FAILURE_REVIEW), never by
    silently falling back to a different data source.
    """
    def __init__(self, tool: FixtureResearchTool, *, extra_tools: dict | None = None):
        self.tool = tool
        self.extra_tools = dict(extra_tools or {})

    def _adapter(self, tool_name: str | None):
        if tool_name in (None, "fixture_research", "document_intelligence"):
            return self.tool
        if tool_name not in self.extra_tools:
            raise RuntimeError(f"no runtime adapter supplied for registered tool {tool_name}")
        return self.extra_tools[tool_name]

    def investigate(self, key: str) -> list[Fact]:
        return self.investigate_with_evidence(key,[]).facts

    def investigate_with_evidence(self,key:str,queries:list[str],*,
                                  tool_name:str|None=None)->ResearchOutcome:
        # The adapter is read-only. It can suggest unverified extracted fact candidates.
        adapter=self._adapter(tool_name)
        if hasattr(adapter,"query_document"):
            outcome=adapter.query_document(key,queries)
            return ResearchOutcome(facts=[f for f in outcome.facts if f.side=="hit"],
                                   document_packets=outcome.document_packets)
        return ResearchOutcome(facts=[f for f in adapter.query(key) if f.side=="hit"])
