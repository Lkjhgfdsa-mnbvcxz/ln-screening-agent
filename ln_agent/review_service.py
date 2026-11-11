"""Small orchestrator integration for durable human review and revisions.

In this version each run re-executes the offline investigation for a hit.
The persisted artifact is human review + append-only decisions, NOT mid-task
checkpoint/resume or external-tool exactly-once execution.
"""
from __future__ import annotations
from .models import Case
from dataclasses import asdict
from hashlib import sha256
import json
from .policy import Policy
from .tools import FixtureResearchTool
from .orchestrator import Orchestrator
from .review_store import ReviewStore

class PersistentReviewService:
    def __init__(self, store: ReviewStore, policy: Policy, tool: FixtureResearchTool):
        self.store = store
        self.policy = policy
        self.tool = tool

    def run_case(self, case: Case) -> dict:
        attestations=[]
        subjects={x.subject_id:x for x in case.subjects}
        for hit in case.hits:
            content={"case_id":case.case_id,"subject":asdict(subjects[hit.subject_id]),
                     "hit":asdict(hit)}
            digest=sha256(json.dumps(content,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            self.store.register_hit(case_id=case.case_id,hit_id=hit.hit_id,
                                    policy_version=self.policy.version,input_hash=digest)
            attestations.extend(self.store.active_attestations(case.case_id,hit.hit_id))
        report=Orchestrator(self.policy,self.tool,
            verification_attestations=attestations,
            authorized_reviewers=self.store.authorized_reviewers).run(case)
        for decision in report["results"]:
            revision, seq = self.store.save_decision(case_id=case.case_id,
                   hit_id=decision["hit_id"],decision=decision)
            decision["review_revision"] = revision
            decision["decision_snapshot_seq"] = seq
        return report
