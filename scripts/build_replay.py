"""Build the public, fully synthetic interactive execution replay.

This runs the real engine against the synthetic WorkBuddy capture example and
embeds the *actual* emitted event stream into a single static HTML file. No
network request, no credential, no real merchant / identity / internal URL is
ever read by this script.

    python3 scripts/build_replay.py --tests 219

Outputs:
    examples/workbuddy_capture_replay.json   machine-readable replay data
    replay.html                             self-contained static replay page

The page lives at the repository root so that GitHub Pages (source: `/`) and a
locally downloaded copy resolve the same relative links. `index.html` (the
Pages entry pointing at `demo.html`) is owned by `scripts/build_demo.py`; this
generator must not overwrite it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ln_agent import Case, FixtureResearchTool, Orchestrator  # noqa: E402
from ln_agent.workbuddy_adapters import (  # noqa: E402
    CaptureBundle, authorized_policy, build_capture_tools,
)

CASE_PATH = ROOT / "examples" / "case_workbuddy_capture.json"
BUNDLE_PATH = ROOT / "examples" / "workbuddy_capture_bundle.json"
REPLAY_JSON = ROOT / "examples" / "workbuddy_capture_replay.json"
REPLAY_HTML = ROOT / "replay.html"

# Aggregated, non-business counters from the final authorized local validation
# run (after the structured-capture and per-hit-note fixes).
# No case id, subject, identifier, URL or free-text evidence is copied here.
AUTHORIZED_RUN_AGGREGATES = {
    "cases": 8,
    "hits": 154,
    "events": 3360,
    # Whole-case wall clocks summed across the 8 cases, which were run one
    # after another in the authorized environment (not started together).
    "engine_ms": 15922.158,
    "wall_ms": 15942.572,
    # 15922.158 / 154 = post-parallel amortised wall share, NOT the duration
    # of a single hit. One hit actually costs ~394.863 ms of engine work.
    "mean_engine_ms_per_hit": 103.391,
    "mean_single_hit_ms": 394.863,
    "sum_single_hit_durations_ms": 60808.866,
    "wall_ms_all_cases_start_together": 9290.271,
    "wall_ms_shared_4_worker_pool": 15202.217,
    "speedup_large_case": 3.97,
    "capture_tool_reads": {
        "workbuddy_browser_readonly": 154,
        "workbuddy_llm_capture": 16,
    },
    "distinct_per_hit_notes": 154,
    "report_drafts": 1,
    "manual_queue_tasks": 0,
    "automatic_sends": 0,
    "automatic_clearances": 0,
    "note": "授权内部环境的聚合计数；不含任何业务字段、工单号或日志正文。",
}

# Literal markers only; the internal host is detected by shape so the public
# repository never has to contain that hostname.
FORBIDDEN = ("LN20", "sk-", "ghp_", "github_pat_", "Bearer ")
INTERNAL_HOST = re.compile(
    r"boss\.[a-z0-9-]+\.(?:com|cn)|@[a-z0-9-]+\.(?:com|cn)\b",
    re.I,
)


def _run_case() -> tuple[dict, list[dict]]:
    case = Case.from_dict(json.loads(CASE_PATH.read_text(encoding="utf-8")))
    bundle = CaptureBundle.from_json(BUNDLE_PATH)
    tools = build_capture_tools(bundle)
    events: list[dict] = []
    lock = threading.Lock()
    t0 = time.perf_counter()

    def emit(event: dict) -> None:
        with lock:
            events.append({
                "seq": len(events) + 1,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
                "kind": event["kind"],
                "stage": event.get("stage") or "orchestrator",
                "hit_id": event.get("hit_id"),
                "status": event.get("status") or "ok",
                "details": event.get("details") or {},
                "duration_ms": event.get("duration_ms"),
            })

    report = Orchestrator(
        authorized_policy(), FixtureResearchTool({}), extra_tools=tools
    ).run(case, max_workers=3, on_event=emit)
    return report, events


def _hit_summaries(report: dict, events: list[dict]) -> list[dict]:
    raw = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    meta = {h["hit_id"]: h for h in raw["hits"]}
    durations = {
        e["hit_id"]: (e.get("details") or {}).get("duration_ms")
        for e in events if e["kind"] == "HIT_FINISHED"
    }
    rows = []
    for r in report["results"]:
        hid = r["hit_id"]
        disp = r["disposition"]
        ev = r["evidence"]
        skills = r["version_snapshot"]["skills"]
        if isinstance(skills, str):
            skills = [s for s in skills.split("+") if s]
        rows.append({
            "hit_id": hid,
            "entity_type": meta[hid]["entity_type"],
            "category": meta[hid]["category"],
            "notes": meta[hid].get("notes", ""),
            "route": r["route"],
            "identity": r["identity"],
            "stop_reason": r["stop_reason"],
            "business_conclusion": disp["business_conclusion"],
            "business_conclusion_status": disp["business_conclusion_status"],
            "final_indicator": disp["final_indicator"],
            "final_indicator_rule": disp["final_indicator_rule"],
            "final_indicator_basis": disp["final_indicator_basis"],
            "conclusion_source": disp["conclusion_source"],
            "recommendation": disp["recommendation"],
            "internal_note": disp["internal_note"],
            "report_recommended": disp["report_recommended"],
            "manual_queue_required": disp["manual_queue_required"],
            "automatically_sent": disp["automatically_sent"],
            "automatically_cleared": disp["automatically_cleared"],
            "duration_ms": durations.get(hid),
            "execution_path": r["execution_path"],
            "skills": skills,
            "tool_usage": r["tried_actions"],
            "research_facts": r["research_facts"],
            "evidence": {
                "exclusion_rules": ev.get("exclusion_rules", []),
                "linked_rules": ev.get("linked_rules", []),
                "soft_signals": ev.get("soft_signals", []),
                "anchors": ev.get("anchors", []),
            },
            "rule_findings": [f["rule_id"] for f in r["rule_findings"]],
            "gate": r["gate"],
            "gate_final_check": r["gate_final_check"],
            "five_why": r["explanation"],
        })
    return rows


def _assert_synthetic(payload: dict) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    for marker in FORBIDDEN:
        if marker in blob:
            raise RuntimeError(f"refusing to publish: found marker {marker!r}")
    if INTERNAL_HOST.search(blob):
        raise RuntimeError("refusing to publish: internal system URL shape")
    if re.search(r"(?<!\d)\d{15,18}(?!\d)", blob):
        raise RuntimeError("refusing to publish: found a document-sized number")
    if not payload["case"]["case_id"].startswith("SYN-"):
        raise RuntimeError("replay case must be synthetic")
    for hit in payload["hits"]:
        if hit["automatically_sent"] or hit["automatically_cleared"]:
            raise RuntimeError("replay contains a forbidden automatic action")
    # Any source_url present must be a synthetic scheme.
    for match in re.findall(r'"source_url"\s*:\s*"([^"]+)"', blob):
        if not match.startswith("synthetic://"):
            raise RuntimeError(f"non-synthetic source_url: {match}")


def build(tests_passed: int | None) -> dict:
    report, events = _run_case()
    raw = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    tool_calls: dict[str, int] = {}
    for e in events:
        if e["kind"] == "TOOL_STARTED":
            name = (e.get("details") or {}).get("tool", "unknown")
            tool_calls[name] = tool_calls.get(name, 0) + 1
    payload = {
        "schema": "ln-agent-replay/1.0",
        "disclaimer": (
            "SYNTHETIC ONLY — 本回放由合成案例经真实引擎执行产生；"
            "不含真实商户、证件、名单条目、内部系统链接或任何业务日志。"
        ),
        "generated_by": "scripts/build_replay.py",
        "case": {
            "case_id": raw["case_id"],
            "subjects": len(raw["subjects"]),
            "hits": len(raw["hits"]),
            "notes": raw.get("notes", ""),
            "sources": ["examples/case_workbuddy_capture.json",
                        "examples/workbuddy_capture_bundle.json"],
        },
        "execution": {
            "event_count": len(events),
            "events": events,
            "stats": report["stats"],
            "policy_version": report["policy_version"],
            "tool_call_distribution": tool_calls,
            "read_only": report["read_only"],
            "human_approval_required": report["human_approval_required"],
        },
        "hits": _hit_summaries(report, events),
        "validation": {
            "authorized_local_aggregates": AUTHORIZED_RUN_AGGREGATES,
            "tests_passed": tests_passed,
            "tests_note": "全量离线回归测试通过（见 README）" if tests_passed else "",
        },
    }
    _assert_synthetic(payload)
    return payload


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LN 筛查 Agent · 合成案例执行回放</title>
<style>
:root{--bg:#f5f7fa;--panel:#ffffff;--panel2:#fafbfd;--border:#e2e7ee;--text:#1b2330;--muted:#687386;--accent:#2563eb;--accent-soft:#eaf1ff;--shadow:0 1px 3px rgba(20,35,60,.06);--code:#0f172a;--codebg:#f3f6fa}
html[data-theme="dark"]{--bg:#11151c;--panel:#1a2029;--panel2:#151b23;--border:#2b3543;--text:#e9eef6;--muted:#9aa8ba;--accent:#7aa5ff;--accent-soft:#1e2c46;--shadow:0 1px 3px rgba(0,0,0,.3);--code:#dce6f5;--codebg:#131a24}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1320px;margin:0 auto;padding:26px 22px 60px}
header.top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;flex-wrap:wrap;margin-bottom:18px}
h1{font-size:25px;line-height:1.3;margin:0 0 8px;letter-spacing:-.3px}
.sub{color:var(--muted);max-width:760px;margin:0}
.badges{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}
.badge{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--accent-soft);color:var(--accent);border:1px solid var(--border)}
.badge.warn{background:#fff5e6;color:#a2600a;border-color:#f1d9ae}
html[data-theme="dark"] .badge.warn{background:#3a2a12;color:#f0c07a;border-color:#5a421d}
.btn{border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:8px;padding:7px 12px;cursor:pointer;font-size:13px;box-shadow:var(--shadow)}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn.primary:hover{opacity:.9;color:#fff}
.stats{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin:18px 0}
.stat{background:var(--panel);border:1px solid var(--border);border-radius:11px;padding:12px 14px;box-shadow:var(--shadow)}
.stat b{display:block;font-size:21px;line-height:1.25;letter-spacing:-.4px}
.stat b.small{font-size:14px;line-height:1.5;letter-spacing:0}
.stat span{color:var(--muted);font-size:12px}
.notice{background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:11px 14px;color:var(--muted);font-size:13px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(0,.92fr);gap:16px;align-items:start}
.card{background:var(--panel);border:1px solid var(--border);border-radius:12px;box-shadow:var(--shadow);overflow:hidden;margin-bottom:16px}
.card h2{font-size:14px;margin:0;padding:12px 15px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:10px}
.card h2 small{font-weight:400;color:var(--muted);font-size:12px}
.body{padding:14px 15px}
.controls{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden}
.seg button{border:0;background:var(--panel);color:var(--muted);padding:6px 10px;cursor:pointer;font-size:12px;border-right:1px solid var(--border)}
.seg button:last-child{border-right:0}
.seg button.on{background:var(--accent-soft);color:var(--accent);font-weight:600}
input[type=range]{width:100%;accent-color:var(--accent)}
.progressrow{display:flex;align-items:center;gap:11px;color:var(--muted);font-size:12px;margin:10px 0 12px}
.progressrow code{font-size:12px;color:var(--text);min-width:74px;text-align:right}
.timeline{position:relative;height:430px;overflow:auto;background:var(--panel2);border:1px solid var(--border);border-radius:9px}
.ev{display:grid;grid-template-columns:44px 92px 1fr auto;gap:9px;align-items:start;padding:8px 11px;border-bottom:1px solid var(--border);font-size:12.5px;cursor:pointer;border-left:3px solid transparent}
.ev:hover{background:var(--accent-soft)}
.ev.past{opacity:.56}
.ev.current{background:var(--accent-soft);border-left-color:var(--accent);opacity:1}
.ev.future{opacity:.78}
.ev .seq{color:var(--muted);font-variant-numeric:tabular-nums}
.ev .stage{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ev .kind{font-weight:600;letter-spacing:.1px;word-break:break-all}
.ev .hit{font-size:11px;color:var(--muted);white-space:nowrap}
.ev .bar{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:1px}
.s-orchestrator{background:#94a3b8}.s-skill{background:#8b5cf6}.s-policy{background:#0ea5e9}.s-risk_gate{background:#f59e0b}.s-rule_engine{background:#10b981}.s-investigation{background:#6366f1}.s-evidence{background:#14b8a6}.s-disposition{background:#ec4899}.s-suspicion{background:#ef4444}
pre{background:var(--codebg);color:var(--code);border:1px solid var(--border);border-radius:8px;padding:11px;overflow:auto;max-height:270px;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;margin:0;white-space:pre-wrap;word-break:break-word}
.kv{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:11px}
.kv span{font-size:11.5px;background:var(--panel2);border:1px solid var(--border);border-radius:6px;padding:3px 8px;color:var(--muted)}
.kv span b{color:var(--text);font-weight:600}
.hitcard{border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:10px;cursor:pointer;background:var(--panel2)}
.hitcard:hover{border-color:var(--accent)}
.hitcard.sel{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
.hitcard .row1{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:7px}
.hitcard .hid{font-weight:700;font-size:13px}
.hitcard .meta{color:var(--muted);font-size:11.5px}
.chip{font-size:12px;font-weight:700;padding:2px 10px;border-radius:999px;border:1px solid var(--border);white-space:nowrap}
.c-none{background:#eef1f5;color:#5b6575}.c-clear{background:#e6f4ff;color:#1668b3}.c-suspect{background:#fff3dc;color:#9a6100}.c-hit{background:#ffe9e9;color:#b3261e}
html[data-theme="dark"] .c-none{background:#252d38;color:#adb8c8}html[data-theme="dark"] .c-clear{background:#17324d;color:#8dc4ff}html[data-theme="dark"] .c-suspect{background:#3d2f13;color:#f4c775}html[data-theme="dark"] .c-hit{background:#451f22;color:#ff9d99}
.note{font-size:12.5px;color:var(--text);margin:6px 0 0}
.path{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}
.path i{font-style:normal;font-size:11px;background:var(--accent-soft);color:var(--accent);border-radius:5px;padding:2px 7px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--muted);font-weight:600;background:var(--panel2)}
ul.guard{margin:0;padding-left:19px;color:var(--muted);font-size:13px}
ul.guard li{margin-bottom:6px}
ul.guard b{color:var(--text)}
footer{margin-top:22px;color:var(--muted);font-size:12.5px;display:flex;gap:16px;flex-wrap:wrap}
@media(max-width:980px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:repeat(3,1fr)}}
@media(max-width:560px){.stats{grid-template-columns:repeat(2,1fr)}.ev{grid-template-columns:36px 70px 1fr}.ev .hit{display:none}}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div>
    <h1>LN 筛查 Agent · 合成案例执行回放</h1>
    <p class="sub">下面的时间线不是手写脚本，而是把 <code>examples/case_workbuddy_capture.json</code> 这份<strong>完全合成</strong>的案例，通过项目真实引擎跑一遍后，由 <code>SKILL_SELECTED / POLICY_CHECK / TOOL_STARTED / FACTS_RECEIVED / RULE_EVALUATED / GATE_CHECK / HIT_RESULT_READY</code> 等真实调用点产生的事件流。</p>
    <div class="badges">
      <span class="badge">合成数据</span><span class="badge">零网络请求</span><span class="badge">单文件静态页</span>
      <span class="badge">8 Skills / 12 Tools</span><span class="badge warn">候选策略 · 未经审批</span>
    </div>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <button class="btn" id="theme">切换深色</button>
    <a class="btn" href="examples/workbuddy_capture_replay.json" download>下载回放 JSON</a>
    <a class="btn primary" href="https://github.com/Lkjhgfdsa-mnbvcxz/ln-screening-agent">下载项目本地运行</a>
  </div>
</header>

<div class="stats" id="stats"></div>
<div class="notice" id="notice"></div>

<div class="grid">
  <div>
    <section class="card">
      <h2>执行时间线 <small id="tlcount"></small></h2>
      <div class="body">
        <div class="controls">
          <button class="btn primary" id="play">▶ 播放</button>
          <button class="btn" id="prev">◀ 上一步</button>
          <button class="btn" id="next">下一步 ▶</button>
          <button class="btn" id="reset">回到开头</button>
          <button class="btn" id="jump">跳到结论</button>
          <div class="seg" id="speed">
            <button data-s="1" class="on">1×</button><button data-s="2">2×</button>
            <button data-s="4">4×</button><button data-s="8">8×</button>
          </div>
        </div>
        <div class="progressrow"><input type="range" id="scrub" min="0" max="1" value="0"><code id="pos">0 / 0</code></div>
        <div class="controls" style="margin-bottom:10px"><div class="seg" id="hitfilter"></div><span style="font-size:12px;color:var(--muted)">空格播放/暂停 · ← → 单步</span></div>
        <div class="timeline" id="timeline"></div>
      </div>
    </section>
    <section class="card">
      <h2>当前事件详情 <small id="curtitle"></small></h2>
      <div class="body"><div class="kv" id="curkv"></div><pre id="curdetail">{}</pre></div>
    </section>
  </div>

  <div>
    <section class="card">
      <h2>逐命中业务结论 <small>点击卡片查看执行路径</small></h2>
      <div class="body" id="hitcards"></div>
    </section>
    <section class="card">
      <h2>选中命中的执行路径与证据 <small id="seltitle"></small></h2>
      <div class="body"><div id="selbody" class="note">选择左侧任一命中卡片。</div></div>
    </section>
    <section class="card">
      <h2>为什么大模型不能自己下结论</h2>
      <div class="body"><ul class="guard">
        <li><b>模型事实恒为未核实。</b> <code>workbuddy_llm_capture</code> 只能输出 <code>model_extracted / checked=false</code>，不满足 <code>eligible_for_hard()</code>，无法触发硬排除或强关联规则。</li>
        <li><b>Tool manifest 围栏。</b> <code>PolicyGuard.validate_facts(..., tool_name=...)</code> 按 <code>tool.json</code> 校验 <code>allowed_fact_origins</code> 与 <code>facts_must_be_unchecked</code>，伪装来源直接抛 <code>PolicyViolation</code>。</li>
        <li><b>Skill 契约决定路由。</b> 下一步动作来自 <code>DecisionRouter</code> + Skill <code>ordered_queries</code>，模型不参与决定调查顺序或终止条件。</li>
        <li><b>默认不授权。</b> 两个本地采集 Tool 都不在默认 <code>Policy.allowed_tool_names</code>，只有显式 <code>authorized_policy()</code> 才启用。</li>
        <li><b>结论仍是草稿。</b> 所有业务结论都是 <code>DRAFT_NOT_APPROVED</code>，不自动发送、不自动放行、不写回业务系统；证据不足时留空结论且不自动创建人工队列。</li>
      </ul></div>
    </section>
  </div>
</div>

<section class="card">
  <h2>验证规模与能力边界 <small>公开页只展示聚合计数，不含业务数据</small></h2>
  <div class="body"><table id="boundary"><thead><tr><th style="width:50%">已接通（本地）</th><th>未接通 / 不属于当前版本</th></tr></thead><tbody></tbody></table></div>
</section>

<footer>
  <a href="README.md">项目 README</a>
  <a href="docs/WORKBUDDY_INTEGRATION.md">接入设计说明</a>
  <a href="examples/case_workbuddy_capture.json">合成案例输入</a>
  <a href="examples/workbuddy_capture_bundle.json">合成采集包</a>
  <span>本页离线可用，不加载任何外部资源。</span>
</footer>
</div>

<script type="application/json" id="replay-data">__REPLAY_DATA__</script>
<script>
(function(){
  "use strict";
  const DATA = JSON.parse(document.getElementById("replay-data").textContent);
  const EV = DATA.execution.events, HITS = DATA.hits;
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  const ms = v => (typeof v === "number" ? v.toFixed(v < 10 ? 2 : 1) + " ms" : "—");

  let view = EV.slice(), idx = 0, playing = false, speed = 1, timer = null, filter = "ALL", selected = HITS[0] ? HITS[0].hit_id : null;

  // ---- header stats -------------------------------------------------------
  const dist = {};
  HITS.forEach(h => { const k = h.business_conclusion || "无结论"; dist[k] = (dist[k]||0)+1; });
  const stats = [
    ["事件", DATA.execution.event_count],
    ["命中", DATA.case.hits],
    ["Tool 调用", Object.values(DATA.execution.tool_call_distribution).reduce((a,b)=>a+b,0)],
    ["引擎耗时", DATA.execution.stats.elapsed_ms.toFixed(1)+" ms"],
    ["结论分布", Object.entries(dist).map(([k,v])=>k+" "+v).join(" / ")],
    ["回归测试", DATA.validation.tests_passed ? DATA.validation.tests_passed+" 项通过" : "见 README"],
  ];
  $("stats").innerHTML = stats.map(([k,v],i)=>`<div class="stat"><b class="${i===4?"small":""}">${esc(v)}</b><span>${esc(k)}</span></div>`).join("");
  const agg = DATA.validation.authorized_local_aggregates;
  $("notice").innerHTML = `<strong>数据来源：</strong>${esc(DATA.disclaimer)} 本页事件来自合成案例的一次真实引擎执行；`
    + `授权内部环境另完成 <b>${agg.cases}</b> 张工单 / <b>${agg.hits}</b> 条命中 / <b>${agg.events}</b> 个事件的聚合验证`
    + `（逐单串行累计墙钟 ${agg.engine_ms.toFixed(0)} ms；单条命中实际 ${agg.mean_single_hit_ms} ms，4 workers 并行后摊到每条 ${agg.mean_engine_ms_per_hit} ms；人工队列 ${agg.manual_queue_tasks}，自动发送 ${agg.automatic_sends}）。`
    + `真实业务数据、完整日志与内部链接仅保留在授权环境，未进入本仓库。`;

  const stageName = {orchestrator:"调度",skill:"Skill",policy:"PolicyGuard",risk_gate:"Risk Gate",rule_engine:"Rule Engine",investigation:"调查",evidence:"证据",disposition:"处置",suspicion:"内部风险"};
  const chip = c => c === "未命中" ? "c-clear" : c === "疑似命中" ? "c-suspect" : c === "命中" ? "c-hit" : "c-none";

  // ---- filters ------------------------------------------------------------
  $("hitfilter").innerHTML = ["ALL"].concat(HITS.map(h=>h.hit_id))
    .map(k=>`<button data-h="${esc(k)}" class="${k==="ALL"?"on":""}">${k==="ALL"?"全部命中":esc(k)}</button>`).join("");
  $("hitfilter").addEventListener("click", e => {
    const b = e.target.closest("button"); if(!b) return;
    filter = b.dataset.h;
    [...$("hitfilter").children].forEach(x=>x.classList.toggle("on", x===b));
    const keep = idx < view.length ? view[idx].seq : -1;
    view = filter === "ALL" ? EV.slice() : EV.filter(x => x.hit_id === filter || x.hit_id === null);
    const at = view.findIndex(x => x.seq === keep);
    idx = at < 0 ? 0 : at;
    renderTimeline(); renderCurrent();
  });

  // ---- timeline -----------------------------------------------------------
  function renderTimeline(){
    $("tlcount").textContent = `${view.length} 个事件 · 过滤：${filter==="ALL"?"全部":filter}`;
    $("timeline").innerHTML = view.map((e,i) =>
      `<div class="ev ${i<idx?"past":i===idx?"current":"future"}" data-i="${i}">`
      + `<span class="seq">#${e.seq}</span>`
      + `<span class="stage"><i class="bar s-${esc(e.stage)}"></i>${esc(stageName[e.stage]||e.stage)}</span>`
      + `<span class="kind">${esc(e.kind)}</span>`
      + `<span class="hit">${esc(e.hit_id||"—")} · ${e.elapsed_ms.toFixed(0)}ms</span></div>`).join("");
    $("scrub").max = Math.max(0, view.length-1);
    $("scrub").value = idx;
    $("pos").textContent = `${view.length?idx+1:0} / ${view.length}`;
  }
  $("timeline").addEventListener("click", e => {
    const row = e.target.closest(".ev"); if(!row) return;
    pause(); idx = +row.dataset.i; renderTimeline(); renderCurrent(); scrollToCurrent();
  });
  function scrollToCurrent(){
    const box = $("timeline"), item = box.querySelector(".ev.current");
    if(item) box.scrollTop = Math.max(0, item.offsetTop - box.clientHeight/2 + item.clientHeight/2);
  }

  function renderCurrent(){
    const e = view[idx]; if(!e) return;
    $("curtitle").textContent = `#${e.seq} · ${e.kind}`;
    $("curkv").innerHTML = [
      ["阶段", stageName[e.stage]||e.stage], ["命中", e.hit_id||"整单"],
      ["状态", e.status], ["已运行", e.elapsed_ms.toFixed(1)+" ms"],
      ["本步耗时", ms(e.duration_ms)], ["策略", DATA.execution.policy_version],
    ].map(([k,v])=>`<span>${esc(k)} <b>${esc(v)}</b></span>`).join("");
    $("curdetail").textContent = JSON.stringify(e.details, null, 2);
    [...$("timeline").children].forEach((el,i)=>{
      el.className = "ev " + (i<idx?"past":i===idx?"current":"future");
    });
    $("scrub").value = idx; $("pos").textContent = `${idx+1} / ${view.length}`;
  }
  function step(n){
    const next = idx + n;
    if(next < 0 || next >= view.length){ if(next>=view.length) pause(); return; }
    idx = next; renderCurrent(); scrollToCurrent();
  }
  function pause(){ playing=false; clearInterval(timer); timer=null; $("play").textContent="▶ 播放"; }
  function play(){
    if(playing){ pause(); return; }
    if(idx >= view.length-1) idx = 0;
    playing=true; $("play").textContent="⏸ 暂停";
    timer = setInterval(()=>step(1), Math.max(55, 430/speed));
    renderCurrent(); scrollToCurrent();
  }
  $("play").onclick = play;
  $("prev").onclick = ()=>{pause();step(-1);};
  $("next").onclick = ()=>{pause();step(1);};
  $("reset").onclick = ()=>{pause();idx=0;renderCurrent();scrollToCurrent();};
  $("jump").onclick = ()=>{
    pause(); const at = view.findIndex(e=>e.kind==="HIT_RESULT_READY");
    idx = at<0 ? view.length-1 : at; renderCurrent(); scrollToCurrent();
  };
  $("scrub").oninput = e => { pause(); idx=+e.target.value; renderCurrent(); scrollToCurrent(); };
  $("speed").addEventListener("click", e=>{
    const b=e.target.closest("button"); if(!b) return;
    speed=+b.dataset.s; [...$("speed").children].forEach(x=>x.classList.toggle("on",x===b));
    if(playing){ pause(); play(); }
  });
  document.addEventListener("keydown", e=>{
    if(["INPUT","TEXTAREA"].includes(document.activeElement.tagName)) return;
    if(e.code==="Space"){ e.preventDefault(); play(); }
    else if(e.key==="ArrowRight"){ e.preventDefault(); pause(); step(1); }
    else if(e.key==="ArrowLeft"){ e.preventDefault(); pause(); step(-1); }
  });
  $("theme").onclick = ()=>{
    const dark = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    $("theme").textContent = dark ? "切换深色" : "切换浅色";
  };

  // ---- hit cards ----------------------------------------------------------
  $("hitcards").innerHTML = HITS.map(h=>
    `<div class="hitcard ${h.hit_id===selected?"sel":""}" data-h="${esc(h.hit_id)}">
      <div class="row1"><span class="hid">${esc(h.hit_id)} <span class="meta">${esc(h.entity_type)} · ${esc(h.category)}</span></span>
      <span class="chip ${chip(h.business_conclusion)}">${esc(h.business_conclusion||"无结论")}</span></div>
      <div class="meta">路由 ${esc(h.route)} · ${esc(h.business_conclusion_status)} · 最终指标 ${esc(h.final_indicator)} (${esc(h.final_indicator_rule)}) · 耗时 ${ms(h.duration_ms)}</div>
      <p class="note">${esc(h.internal_note||"证据不足，未形成业务结论。")}</p>
      <div class="path">${h.execution_path.slice(0,8).map(p=>`<i>${esc(p.action)}</i>`).join("")}</div>
    </div>`).join("");
  $("hitcards").addEventListener("click", e=>{
    const card=e.target.closest(".hitcard"); if(!card) return;
    selected=card.dataset.h;
    [...$("hitcards").children].forEach(x=>x.classList.toggle("sel",x===card));
    renderSelected();
  });

  function li(v){ return Array.isArray(v)&&v.length ? v.map(x=>`<li>${esc(typeof x==="object"?JSON.stringify(x):x)}</li>`).join("") : "<li>—</li>"; }
  function renderSelected(){
    const h = HITS.find(x=>x.hit_id===selected); if(!h) return;
    $("seltitle").textContent = `${h.hit_id} · ${h.route}`;
    const facts = h.research_facts || [];
    const unchecked = facts.filter(f=>f.checked===false).length;
    $("selbody").innerHTML = `
      <div class="kv">
        <span>结论 <b>${esc(h.business_conclusion||"无结论")}</b></span>
        <span>最终指标 <b>${esc(h.final_indicator)}</b> (${esc(h.final_indicator_rule)})</span>
        <span>建议 <b>${esc(h.recommendation)}</b></span>
        <span>停止原因 <b>${esc(h.stop_reason)}</b></span>
        <span>上报草稿 <b>${h.report_recommended?"是":"否"}</b></span>
        <span>人工队列 <b>${h.manual_queue_required?"是":"否"}</b></span>
        <span>自动发送 <b>${h.automatically_sent?"是":"否"}</b></span>
      </div>
      <p class="note"><b>最终指标依据</b>：${(h.final_indicator_basis||[]).map(esc).join("；")}（派生统计口径，不改变业务结论、不自动放行）</p>
      <p class="note"><b>执行路径</b></p>
      <div class="path">${h.execution_path.map((p,i)=>`<i>${i+1}. ${esc(p.action)}${p.tool?" · "+esc(p.tool):""}${p.key?" · "+esc(p.key):""}</i>`).join("")}</div>
      <p class="note" style="margin-top:12px"><b>Skill 契约</b>：${h.skills.map(esc).join(" · ")}</p>
      <p class="note"><b>Tool 调用</b>：${h.tool_usage.length?h.tool_usage.map(t=>`${esc(t.tool)} → ${esc(t.outcome)}（${t.new_fact_candidates} 条候选）`).join("；"):"无"}</p>
      <p class="note"><b>规则命中</b>：${h.rule_findings.join("、")||"无"}；强关联 ${h.evidence.linked_rules.join("、")||"无"}；排除 ${h.evidence.exclusion_rules.join("、")||"无"}；软信号 ${h.evidence.soft_signals.join("、")||"无"}</p>
      <p class="note"><b>风险门</b>：${esc((h.gate.conditions||[]).join("、")||"无标志")}</p>
      <p class="note"><b>来源证据</b>：共 ${facts.length} 条调研事实，其中 ${unchecked} 条为模型未核实候选（不得触发硬规则）。</p>
      <pre>${esc(JSON.stringify({research_facts:facts, evidence_anchors:h.evidence.anchors, five_why:h.five_why}, null, 2))}</pre>`;
  }

  // ---- boundary table -----------------------------------------------------
  const yes = [
    "确定性规则 / Evidence / Risk Gate / PolicyGuard / Decision Router",
    "多命中并行 + SSE 实时工作台（本地 127.0.0.1）",
    "8 个 Skill 契约 + 12 个 Tool 描述与权限登记",
    "WorkBuddy 授权本地只读浏览器采集（boss: 前缀）",
    "WorkBuddy 会话内模型 staged 抽取（model: 前缀，零外部 API）",
    "合成案例、离线回放、简洁业务说明与未发送的上报草稿",
  ];
  const no = [
    "真实 LN / BOSS / 企查查 / 官方登记处在线只读接口",
    "官方与监管名单在线鉴真（如 BIS Entity List）",
    "公网 Python 后端与生产级身份认证",
    "自动审批 / 自动放行 / 自动发送 / 向业务系统写回",
    "任意用户文档上传与长期任务完整断点恢复",
    "外部 OpenAI-compatible 自动调查主流程（仍为可选、未接通）",
  ];
  $("boundary").querySelector("tbody").innerHTML = `<tr><td><ul class="guard">${li(yes)}</ul></td><td><ul class="guard">${li(no)}</ul></td></tr>`;

  renderTimeline(); renderCurrent(); renderSelected();
})();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", type=int, default=None,
                    help="number of passing offline regression tests to display")
    args = ap.parse_args()
    payload = build(args.tests)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    REPLAY_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    safe = data.replace("</", "<\\/")
    REPLAY_HTML.write_text(HTML.replace("__REPLAY_DATA__", safe), encoding="utf-8")
    stale = ROOT / "docs" / "replay.html"
    if stale.exists():
        stale.unlink()
    print(f"events={payload['execution']['event_count']} hits={len(payload['hits'])} "
          f"engine_ms={payload['execution']['stats']['elapsed_ms']}")
    for path in (REPLAY_JSON, REPLAY_HTML):
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
