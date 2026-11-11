"""Bounded in-memory runs, per-hit incremental events and real measured timings.

Synthetic fixtures only. Event JSONL is local and gitignored. No network tools,
LLM service, BOSS authentication or real internal merchant data integration.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Condition, Lock, Thread
from time import monotonic
from uuid import uuid4
from typing import Any
from .. import Case, Policy, Orchestrator, FixtureResearchTool
from ..skill_catalog import PRIMARY, ADDITIONAL, load_skill
from ..tool_catalog import tool_status
from .prior import PriorDisposition, compare_prior

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = {
    "multi": {"title":"12 条混合命中 · 并行 + 资料调查", "case":"examples/demo_case.json",
              "research":"examples/research_fixtures.json"},
    "strong_link": {"title":"企业强关联 · 合成案例", "case":"examples/case_true_link.json"},
    "false_positive": {"title":"人员排除候选 · 合成案例", "case":"examples/case_false_positive.json"},
    "company_risk": {"title":"重大名单风险 · 合成企业", "case":"examples/case_company_critical_suspected.json"},
    "person_risk": {"title":"核心身份信息一致 · 合成人员", "case":"examples/case_person_identity_suspected.json"},
    "workbuddy_capture": {"title":"WorkBuddy 本地采集 · 合成回放", "case":"examples/case_workbuddy_capture.json",
                          "capture":"examples/workbuddy_capture_bundle.json"},
}

@dataclass
class RunRecord:
    run_id: str
    case_key: str
    case_id: str
    hit_ids: tuple[str, ...]
    started_monotonic: float = field(default_factory=monotonic)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_monotonic: float | None = None
    status: str = "running"
    events: list[dict] = field(default_factory=list)
    decisions: dict[str, dict] = field(default_factory=dict)
    prior_comparisons: dict[str, dict] = field(default_factory=dict)
    report: dict | None = None
    error: str = ""
    cond: Condition = field(default_factory=Condition, repr=False)

    def add(self, event: dict):
        with self.cond:
            row = {"seq":len(self.events)+1,
                   "time":datetime.now(timezone.utc).isoformat(),
                   "elapsed_ms":round((monotonic()-self.started_monotonic)*1000, 3),
                   **event}
            if row.get("kind") == "HIT_RESULT_READY":
                self.decisions[row["hit_id"]] = row["details"].pop("decision")
            self.events.append(row)
            self.cond.notify_all()
            return row

    def snapshot(self) -> dict:
        with self.cond:
            perf = {}
            for e in self.events:
                if isinstance(e.get("duration_ms"), (int, float)):
                    k = e.get("stage") or "other"
                    r = perf.setdefault(k,{"count":0,"duration_ms":0.0})
                    r["count"] += 1
                    r["duration_ms"] += e["duration_ms"]
            for item in perf.values():
                item["duration_ms"] = round(item["duration_ms"], 3)
            return {
                "run_id":self.run_id, "case_key":self.case_key,"case_id":self.case_id,
                "hit_ids":list(self.hit_ids),"status":self.status,
                "started_at":self.started_at,
                "elapsed_ms":round(((self.finished_monotonic if self.finished_monotonic is not None else monotonic())-self.started_monotonic)*1000,3),
                "event_count":len(self.events),"completed":len(self.decisions),
                "report_ready":self.report is not None,
                "decisions":dict(self.decisions),"prior_comparisons":dict(self.prior_comparisons),
                "performance":perf,"stats":self.report.get("stats",{}) if self.report else {},
                "error":self.error,
            }

class WorkbenchRunner:
    def __init__(self, *, audit_dir: Path | None = None, persist_audit: bool = True,
                 max_runs: int = 12):
        self.runs: dict[str, RunRecord] = {}
        self.lock = Lock()
        self.max_runs = max_runs
        self.persist_audit = persist_audit
        self.audit_lock = Lock()
        self.audit_dir = audit_dir or ROOT / ".local" / "runs"
        if persist_audit:
            self.audit_dir.mkdir(parents=True,exist_ok=True)

    def capabilities(self) -> dict:
        from ..llm_adapter import LLMConfig
        llm=LLMConfig.from_env().status()
        from ..workbuddy_adapters import BROWSER_TOOL, LLM_TOOL
        return {"mode":"synthetic_offline", "has_real_llm":llm["configured"],"llm":llm,"has_external_tools":False,
                "skills":[{"slug":slug,"id":load_skill(slug)["id"]}
                          for slug in list(PRIMARY.values())+sorted(ADDITIONAL)],
                "tools":tool_status(),"cases":{k:v["title"] for k,v in EXAMPLES.items()},
                "workbuddy_local_adapters":[BROWSER_TOOL, LLM_TOOL],
                "policy":"CANDIDATE / NOT APPROVED", "external_writeback":False}

    def start(self, key: str, workers: int = 4) -> RunRecord:
        if key not in EXAMPLES:
            raise ValueError("unsupported demo case")
        if type(workers) is not int or not 1 <= workers <= 8:
            raise ValueError("workers must be 1..8")
        cfg = EXAMPLES[key]
        case = Case.from_dict(json.loads((ROOT / cfg["case"]).read_text(encoding="utf-8")))
        with self.lock:
            if len(self.runs) >= self.max_runs:
                # Remove a finished run, never silently interrupt an active run.
                old = next((rid for rid,r in self.runs.items() if r.status != "running"),None)
                if old is None: raise RuntimeError("active run capacity reached")
                del self.runs[old]
            run = RunRecord(uuid4().hex[:12],key,case.case_id,tuple(h.hit_id for h in case.hits))
            self.runs[run.run_id] = run
        Thread(target=self._execute,args=(run,case,cfg,workers),daemon=True).start()
        return run

    def _execute(self, run: RunRecord, case: Case, cfg: dict, workers: int):
        def emit(event):
            row = run.add(event)
            if self.persist_audit:
                with self.audit_lock:
                    with (self.audit_dir / f"{run.run_id}.jsonl").open("a", encoding="utf-8") as output:
                        output.write(json.dumps(row,ensure_ascii=False)+"\n")
        try:
            # Demonstration of read-only prior dispositions; never used as Rule Engine Facts.
            prior_raw = json.loads((ROOT / "examples/prior_reviews_synthetic.json").read_text(encoding="utf-8"))
            priors = {}
            for item in prior_raw:
                p = PriorDisposition.from_dict(item)
                if p.case_id == case.case_id and p.hit_id in run.hit_ids:
                    priors[p.hit_id] = p
                    emit({"kind":"PRIOR_REVIEW_READ","stage":"prior_review", "case_id":case.case_id,
                          "hit_id":p.hit_id,"status":"unverified_import",
                          "details":{"conclusion":p.conclusion,"source_ref":p.source_ref,
                                     "policy_effect":"none; display only"}})
            fixture = (json.loads((ROOT / cfg["research"]).read_text(encoding="utf-8"))
                       if "research" in cfg else {})
            policy, extra_tools = Policy(), {}
            if "capture" in cfg:
                # Synthetic bundle only. Real authorized bundles are never in the repo.
                from ..workbuddy_adapters import (CaptureBundle, authorized_policy,
                                                  build_capture_tools)
                bundle = CaptureBundle.from_json(ROOT / cfg["capture"])
                extra_tools = build_capture_tools(bundle)
                policy = authorized_policy(policy)
                emit({"kind":"CAPTURE_ADAPTERS_ENABLED","stage":"policy","case_id":case.case_id,
                      "hit_id":None,"status":"ok","details":{"tools":sorted(extra_tools),
                                                             "bundle":"synthetic_local_only"}})
            report = Orchestrator(policy,FixtureResearchTool(fixture),extra_tools=extra_tools).run(
                case,max_workers=workers,on_event=emit)
            for decision in report["results"]:
                prior = priors.get(decision["hit_id"])
                if prior:
                    compare = compare_prior(prior,decision)
                    with run.cond:
                        run.prior_comparisons[decision["hit_id"]] = compare
                    emit({"kind":"PRIOR_COMPARISON", "stage":"prior_review","case_id":case.case_id,
                          "hit_id":decision["hit_id"],"status":"ok",
                          "details":{"comparison":compare["comparison"],"prior_immutable":True}})
            with run.cond:
                run.report = report
                run.status = "completed"
                run.finished_monotonic = monotonic()
                run.cond.notify_all()
        except Exception as e:
            with run.cond:
                run.status = "failed"
                run.finished_monotonic = monotonic()
                run.error = f"{type(e).__name__}: {e}"[:300]
                run.cond.notify_all()
            emit({"kind":"RUN_FAILED","stage":"orchestrator","case_id":case.case_id,
                  "hit_id":None,"status":"error","details":{"error_type":type(e).__name__}})

    def get(self, run_id: str) -> RunRecord:
        with self.lock:
            if run_id not in self.runs:
                raise KeyError(run_id)
            return self.runs[run_id]
