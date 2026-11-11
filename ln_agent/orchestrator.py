"""Multi-hit concurrent orchestration with isolated conclusions and common read cache."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from .models import Case
from .policy import Policy
from .tools import FixtureResearchTool, InvestigationAgent
from .router import DecisionRouter
from .fact_verification import FactVerifier,ReviewAttestation

class Orchestrator:
    def __init__(self, policy: Policy, tool: FixtureResearchTool,
                 *, verification_attestations: list[ReviewAttestation] | None = None,
                 authorized_reviewers: frozenset[str] = frozenset()):
        self.policy = policy
        self.tool = tool
        self.router = DecisionRouter(policy, InvestigationAgent(tool),
            FactVerifier(attestations=verification_attestations,
                         authorized_reviewers=authorized_reviewers))

    def run(self, case: Case, max_workers: int = 4) -> dict:
        if not case.hits:
            return {"case_id": case.case_id, "results": [], "stats": {"hits": 0}}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(case.hits))) as pool:
            decisions = list(pool.map(lambda hit: self.router.run_hit(case, hit), case.hits))
        return {
            "case_id": case.case_id,
            "policy_version": self.policy.version,
            "read_only": True,
            "human_approval_required": True,
            "results": [x.to_dict() for x in decisions],
            "stats": {"hits": len(decisions), "fixture_source_reads": self.tool.read_count},
        }
