"""Multi-hit concurrent orchestration with isolated conclusions and common read cache."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Callable
from .models import Case
from .policy import Policy
from .tools import FixtureResearchTool, InvestigationAgent
from .router import DecisionRouter
from .fact_verification import FactVerifier,ReviewAttestation

class Orchestrator:
    def __init__(self, policy: Policy, tool: FixtureResearchTool,
                 *, verification_attestations: list[ReviewAttestation] | None = None,
                 authorized_reviewers: frozenset[str] = frozenset(),
                 extra_tools: dict | None = None):
        self.policy = policy
        self.tool = tool
        self.extra_tools = dict(extra_tools or {})
        self.router = DecisionRouter(policy, InvestigationAgent(tool, extra_tools=self.extra_tools),
            FactVerifier(attestations=verification_attestations,
                         authorized_reviewers=authorized_reviewers))

    def run(self, case: Case, max_workers: int = 4,
            on_event: Callable[[dict], None] | None = None) -> dict:
        started = perf_counter()
        def emit(event: dict):
            if on_event is not None:
                try: on_event(event)
                except Exception: pass
        emit({"kind":"CASE_STARTED","stage":"orchestrator","case_id":case.case_id,
              "hit_id":None,"details":{"hits":len(case.hits),"max_workers":max_workers},"status":"ok"})
        if not case.hits:
            return {"case_id": case.case_id, "results": [], "stats": {"hits": 0}}
        decisions = [None] * len(case.hits)
        with ThreadPoolExecutor(max_workers=min(max_workers, len(case.hits))) as pool:
            futures = {pool.submit(self.router.run_hit, case, hit, on_event=emit): idx
                       for idx, hit in enumerate(case.hits)}
            for future in as_completed(futures):
                idx = futures[future]
                decisions[idx] = future.result()
                emit({"kind":"HIT_RESULT_READY","stage":"orchestrator", "case_id":case.case_id,
                      "hit_id":case.hits[idx].hit_id,"status":"ok",
                      "details":{"decision":decisions[idx].to_dict()}})
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        emit({"kind":"CASE_FINISHED","stage":"orchestrator","case_id":case.case_id,
              "hit_id":None,"status":"ok","duration_ms":elapsed_ms,
              "details":{"hits":len(decisions)}})
        return {
            "case_id": case.case_id,
            "policy_version": self.policy.version,
            "read_only": True,
            "human_approval_required": True,  # formal LN writeback only; NOT a research queue
            "manual_investigation_queue_default": False,
            "results": [x.to_dict() for x in decisions],
            "stats": {"hits": len(decisions), "elapsed_ms": elapsed_ms, "fixture_source_reads": self.tool.read_count,
                      "capture_tool_reads": {name: getattr(adapter, "read_count", 0)
                                             for name, adapter in self.extra_tools.items()},
                      "report_drafts": sum(1 for d in decisions if d.disposition.get("report_recommended")),
                      "manual_queue_tasks": sum(1 for d in decisions if d.disposition.get("manual_queue_required"))},
        }
