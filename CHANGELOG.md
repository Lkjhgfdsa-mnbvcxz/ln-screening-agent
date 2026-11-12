## V0.9.7 — Plain-language, DISPLAY-ONLY explanation layer

> Reviewer feedback: "不是你看这个结果像人话吗 谁看得懂啊 到底是怎么命中的 其他排除是怎么排除",
> and "这个专家，谁会让你跑 demo 啊，第一条应该是让他去查这个命中没命中不良记录".

### What changed (display only — the decision chain is untouched)

- **No new decision logic.** `Rule Engine → PolicyGuard → Risk Gate → Decision Router → Disposition`,
  FI-1/2/3, `business_conclusion`, `recommendation`, `route`, evidence, timing and the model-fact
  boundary are all unchanged. The new code only *describes* an already-final decision.
- New `ln_agent/plain_language.py` builds `plain_summary` from existing deterministic fields only:
  `kind="DISPLAY_ONLY"`, `headline`, `compare` (field-by-field `入网主体 / 名单记录 / 结果` rows),
  `why`, `why_not`, `next_step`, `evidence`, `caveat`, plus three always-false flags.
  It never creates a `Fact`, never calls a model/tool, never sets `checked`.
- `build_disposition()` attaches `plain_summary` **after** every decision field is final.
  `skills/disposition_reporting/contract.json` v1.2 adds a `display_layer` section and makes
  `plain_summary` a required output field; `PolicyGuard.validate_disposition_draft()` now rejects
  a missing summary, a non-`DISPLAY_ONLY` kind, a tampered flag, an empty comparison, and any
  unresolved hit whose `why_not` fails to say it is **not** a clearance.
- **Self-consistency fixes found while writing the layer**: soft fields (address / region) are
  never described as hard exclusions; a confirmed hit with a differing address no longer claims
  "no conflicts"; company hits no longer print "企业注册号、企业注册号"; raw ids such as `dob`
  are translated to Chinese; the decisive FI basis (e.g. "政策阻断，不得归入误报") is now shown
  instead of only the first two items; the `business_conclusion` vs `final_indicator` two-axis
  difference is explained when they disagree.
- **Public demo** (`scripts/build_demo.py`, schema `ln-agent-demo-workbench/1.3`): home page gains
  "这一批是怎么判的 · 先看这里" (4 plain-language cards covering 命中 / 疑似命中 / 误报·未命中 /
  why large batches group as false positives). Every one of the 154 hits gets a unique
  `explanation` (tag / headline / field comparison / why / why_not / next_step / evidence /
  caveat) and `path_cn`. Machine fields move into a collapsed `<details class="ex-tech">`.
  Excluded hits now explain the exact conflicting field and both values, and state that a
  `误报·未命中` indicator is only a review-priority label, not a clearance.
- **Live workbench** (`app.js` / `style.css`): `plain_summary` is the primary card — headline,
  colour-coded comparison table, why / why-not / next step / evidence / caveat. `internal_note`,
  route, rule ids, technical status and raw execution path move into the collapsed
  "查看技术字段与执行路径（给开发 / 审计看）" block.
- **Replay** (`scripts/build_replay.py`): each hit carries `plain_summary`; hit cards lead with its
  headline and the detail pane renders the same plain-language card.
- **WorkBuddy Agent expert** (`ln-screening-expert` v1.1.0): `defaultInitPrompt` and the first
  quick prompts are now business verification questions ("does this hit have an adverse record,
  is it a real hit, which fields were compared, how were the others excluded") instead of
  "run the demo". The Agent MD adds a "第零原则：先回答业务问题" and a hard plain-language output
  spec that bans status codes as the primary display.
- New `docs/PLAIN_LANGUAGE.md` documents the boundary and the field contract.
- Tests: 2 new demo tests + 15 new `tests/test_plain_language.py` tests, **259 passing**.
  Regenerated `demo.html`, `replay.html`, `index.html` and both example JSON payloads.

## V0.9.6 — Final indicator (FI-1/2/3), publication gate, history scrub

### Final indicator: explicit outcome for every hit, one batch-level metric

- New `ln_agent/final_indicator.py` derives a **downstream, read-only triage metric** strictly after `build_disposition()`, consuming only rule/evidence outputs the existing pipeline already produced. No model call, no new fact, no new decision.
  - **FI-1 命中**: confirmed `business_conclusion == "命中"` + `identity == "strong_link"`; hard match rules recorded in the basis.
  - **FI-2 疑似命中**: existing report draft / mandatory escalation / **serious source-attributed event AND consistent incident location**; policy blocks and source conflicts are also retained here (never grouped as false positives).
  - **FI-3 误报·未命中**: no material risk information — e.g. identity fields that only the notice carries cannot be obtained and nothing serious is attached. Grouped for statistics / review priority only.
- "事发地一致" is an exact normalised match between explicit structured location fields; missing values are UNKNOWN, never "consistent"; masked values never participate.
- `final_indicator_does_not_clear_hit` is always `True` and `final_indicator_changes_business_conclusion` always `False`. `PolicyGuard.validate_disposition_draft()` rejects unknown labels, tampered status/basis, upgrading an unconfirmed hit, downgrading a confirmed/suspected hit, and any attempt to clear a hit. `skills/disposition_reporting/contract.json` declares the derived metric separately from `prohibited_shortcuts`, so the original "信息不足自动判误报" guard on the real disposition is intact.
- `derive_case_indicator()` rolls hits up to a checklist-level indicator, distribution and escalation rate. Batch metric: **需人工复核率 =（命中 + 疑似命中）/ 全部命中**.
- Live workbench (`app.js` / `style.css`) shows the indicator and its basis in a visually distinct panel below the business verdict; the hit list shows it too. `replay.html` shows the indicator, rule id and basis per hit.
- Public demo schema bumped to `ln-agent-demo-workbench/1.2`: home page has a **final indicator panel** (rules + 3-way distribution + 11.0% escalation rate), every case card has a case-level indicator, every hit has both `业务结论` and `最终指标` plus `指标依据`, and the hit filter is by final indicator. Five synthetic hits demonstrate the reviewer's rule "same missing identity information, but serious + consistent incident location ⇒ 疑似命中" while their business conclusion stays `无法确定`.
- 14 new tests in `tests/test_final_indicator.py`; `tests/test_public_demo.py` gains a full indicator-consistency test.

### Sensitive data hidden, then synced

- Replaced the USCC-shaped synthetic token in public examples with a clearly non-identifier value (`SYNTH-USCC-00017`) so even the *shape* of a real registration number is gone.
- New `scripts/check_sensitive.py` publication gate scans every tracked/pending text file **and every published git revision** for real-shaped case ids, internal hosts, provider secrets, platform tokens, identity numbers, USCCs, internal review routes and capture markers. Patterns are assembled from fragments so the gate itself stores no real value; an optional out-of-repo vocabulary can be supplied with `--vocab`.
- The **initial commit's test file contained a real case id and real company names**. Git history was rewritten to remove that file from every revision; `tests/test_publication_gate.py` (8 tests) now fails the build if any real-shaped case id reappears in history or the working tree.
- New `docs/FINAL_INDICATOR.md` documents the exact rule, the boundary, and the "based on the project + fixed project defects" optimisation list. README / AGENTS / WORKBENCH / examples README updated accordingly.
- Full suite: **242 tests passing**.

## V0.9.5 — Concurrency semantics corrected (m subjects start together)

- **The published timing model was wrong.** `Orchestrator.stats.elapsed_ms` is the whole-case wall clock *after* the 4-worker `ThreadPoolExecutor`, not the sum of per-hit work. The authorized runner also read `HIT_FINISHED.duration_ms` from `details` instead of the event's top-level field, producing 154 nulls. As a result the demo treated the post-parallel share `103.391 ms` as if it were one hit's cost, divided by 4 a second time (double-counted speedup), and labelled the serial sum of eight case wall clocks as "parallel wall time".
- Recomputed from the real event logs: **one hit costs 394.863 ms on average** (median 389.985 ms, 60,808.866 ms total work); a 49-hit case reaches **3.93x** and an 88-hit case **3.97x** with 4 workers; the eight cases were actually run **one after another** for a cumulative 15,922.158 ms wall clock; `103.391 ms/hit` is only `15922.158 / 154`, i.e. the amortised wall share.
- Three explicit wall-clock figures now coexist in the demo data: `wall_ms_all_cases_together` (8 subjects start together, 4 workers each = 32 concurrent, wall = slowest case ≈ 9.3 s), `wall_ms_shared_pool` (one shared 4-worker pool ≈ 15.2 s) and `wall_ms_serial_cases` (authorized local measurement ≈ 15.9 s). The page explains why one hit's duration can never finish 154 hits with finite workers.
- Demo animation now starts all 8 cards at t=0 with per-case duration proportional to that case's own wall clock, and per-hit stages advance in waves of 4 instead of one by one. `stage_ms` is derived from each hit's duration so the 5-stage bar is internally consistent.
- Schema bumped to `ln-agent-demo-workbench/1.1`; `tests/test_public_demo.py` adds a concurrency-model test. README / CHANGELOG / AGENTS / WORKBENCH / examples README and the replay's aggregate notice now distinguish single-hit cost from amortised wall share. **219 tests passing.**

## V0.9.4 — Checklist-level public demo workbench + real-run data fixes

### New public demo (`demo.html`, now the Pages entry)

- `scripts/build_demo.py` is the only generator of `demo.html`, `examples/demo_workbench_data.json` **and** `index.html`; `scripts/build_replay.py` no longer writes `index.html`, so regenerating the replay can silently undo the demo entry.
- The demo is organised the way reviewers asked: **8 checklist subject cards on the home page → click one → every hit's 5-stage progress, final business conclusion, and its own per-hit reason / execution path**. Large checklists (88 / 49 hits) are first-class; deep links (`demo.html#SYN-LN-2602`) and one-click auto-run (`demo.html?autorun=1`) work without a backend.
- Added a **subject profile** whose field schema comes from the WorkBuddy Qichacha connector (`get_company_profile`, `get_company_risk_scan`, `get_executive_risk_scan`): enterprise 35 risk dimensions / person 18, industry, scale, employees, affiliated companies, roles, USCC anchor. All values are synthetic and labelled as such; the live connector call returned `402 credit_balance_insufficient`, so no real query is claimed. The connector discipline "0 hits in structured dimensions ≠ no risk" is displayed verbatim on the page.
- Timing model corrected: `engine_ms` is the sum of per-hit costs, `wall_ms = engine_ms / 4 workers`, `mean_ms_per_hit = engine_ms / hits`; no longer divides parallel wall time by hit count a second time.
- 10 new tests in `tests/test_public_demo.py` lock the synthetic-only guard, the 8/154 shape, per-hit reasons, QCC profile, timing math, embedded-data consistency, zero external resources, deep links / auto-run, reproducibility and Pages entry ownership. Full suite: **218 tests passing**.

### Authorized-run fixes (local only; public pages carry aggregates only)

- `build_authorized_cases.py` previously fed only the subject name to the engine and dropped `分数 / 记录源 / ID号码 / LN报警ID / 地址 / 申请人统一信用代码`. Rebuilt `Hit.risk_event` with score, primary source, source domains, material context and applicant-side USCC (`kyb_verified`). After the fix one real checklist changed from "no conclusion" to **疑似命中** with an unsent report draft, and another entered `EVIDENCE_CONFLICT_REVIEW` on a USCC conflict.
- `disposition.py` insufficient-evidence branch swallowed `risk_event.material_context` and emitted 7 boilerplate notes. It now writes the hit's own source domain, LN record id and missing identity fields; `internal_note` limit raised to 900 and double full stops stripped. **154 / 154 notes are distinct**; `tests/test_per_hit_reason.py` (5 tests) locks the behaviour and forbids "误报" / clearance language.
- Final authorized aggregate: 8 cases / 154 hits / 3,360 events, engine 15,922.158 ms, wall 15,942.572 ms, **103.391 ms per hit**, browser reads 154, model captures 16, one 疑似命中, one `EVIDENCE_CONFLICT_REVIEW`, 153 `RESIDUAL_SUSPICION`, report drafts 1, manual queues 0, automatic sends/clearances 0. These supersede the earlier V0.9.3 numbers (7,913.154 ms / 51.384 ms per hit / 3,362 events).
- README now leads with the hosted demo, three real screenshots in `assets/`, the corrected aggregates, and the connected / not-connected list. Existing localhost SSE workbench is unchanged.

## V0.9.3 — Authorized local WorkBuddy capability adapters

### Public synthetic execution replay

- `scripts/build_replay.py` runs the synthetic WorkBuddy capture case through the real engine and publishes the actual emitted event stream as `examples/workbuddy_capture_replay.json`.
- `replay.html` is a self-contained interactive static replay (play / pause / step / speed / hit filter / event JSON / per-hit evidence / Five-Why) with **zero external resources**; `index.html` redirects the GitHub Pages root to it. Links resolve identically on Pages and from a downloaded copy.
- The generator refuses to publish real-data markers (`LN20...`, internal hosts, credentials, document-sized numbers, non-synthetic `source_url`, automatic sends). `tests/test_public_replay.py` locks the sanitizer, the embedded data, the no-external-resource guarantee and event-stream reproducibility.
- Only aggregate, non-business counters from the authorized 8-case / 154-hit validation are shown publicly (0 manual queues, 0 automatic sends). The counters in this release were superseded by the final V0.9.4 run; see that section for the current numbers. Real captures, full logs and internal URLs remain in the authorized environment.
- README now links the hosted replay, documents the connected / not-connected list and the validation results. Existing localhost SSE workbench is unchanged.
- Fixed `ReviewStore.backup()` leaking a sqlite handle (a `Connection` context manager only scopes a transaction); added a regression test that asserts both handles are closed.

- Added `workbuddy_browser_readonly` and `workbuddy_llm_capture` tool manifests plus the `workbuddy_capture` auxiliary Skill contract; both tools are **local-only** and excluded from the default Policy allowlist.
- `InvestigationAgent` can now dispatch to registered adapters; `DecisionRouter` resolves the tool from the source-key prefix via `tool_catalog.tool_for_source_key()` instead of a hardcoded branch. The evidence/PolicyGuard/RiskGate/Disposition flow is unchanged.
- `PolicyGuard.validate_facts()` now enforces manifest-declared `allowed_fact_origins` / `facts_must_be_unchecked`, so a model cannot self-verify or impersonate an authorized source adapter.
- In-session model extraction is replayed through the project's own `LLMExtractionAdapter` with a staged, non-network transport; output is always `model_extracted / checked=false` and can never trigger a hard rule.
- Added a fully synthetic `workbuddy_capture` example + bundle, a workbench case, 16 regression tests, and `docs/WORKBUDDY_INTEGRATION.md`.

### Defects found on 8 authorized real checklists (154 hits) and fixed

- `risk_categories()` did not recognize the Chinese provider labels `制裁 / 执法 / PEP / 不利媒体` used on BOSS pages. As a result `RiskGate` omitted `SCREENING_REVIEW_REQUIRED` and `reportable_risk_categories` never matched. Added aliases + regression tests; after the fix all 49 sanctions hits retain the mandatory screening-review flag.
- `Decision` did not export facts acquired during bounded research. Added `Decision.research_facts` with source tool, action key, origin, checked state, evidence id and source URL, so every hit has a complete sourced evidence record.
- `build_disposition()` computed the concise internal note from the original `hit.facts` only, hiding a decisive DOB conflict discovered by an authorized source adapter. It now receives all facts known at disposition time; regression test asserts the DOB difference appears.
- Added a regression test locking the deliberate disagreement with human `误报` conclusions based on province/address differences: the engine must not lower its evidence threshold to match them, and must not create a human investigation queue on insufficient evidence.
- Full suite: 203 tests passing (16 adapter guard tests, 8 real-shape regression tests, 9 public-replay safety tests, plus the existing suite; the sqlite handle assertion was added to the existing backup test).

## V0.9.2 — Business outcomes in Web workbench

- Business-facing conclusion is one of `未命中 / 疑似命中 / 命中` or null if not established; all are drafts.
- Workbench list and detail now show the business outcome; route/debug state moved behind a disclosure panel.
- Prior human dispositions are displayed in Chinese separately, never adopted as evidence.
- JSON reporting and disposition skill contract carry the same business outcome and approval state.
- Regression tests cover all outcomes, insufficient evidence, and guard constraints.

## V0.9.1 — Lean repository cleanup

- Removed redundant legacy Git/merge documents, historical one-off demos and unneeded fixture-regenerator script.
- Compressed dashboard preview to WebP; retained all 7 Skills, 10 Tool manifests, runtime code, workbench and regression tests.
- Refreshed GitHub README and relative documentation references; **no changes to screening decisions**.

# Changelog

## v0.9 — Local Workbench & Optional Model Interface (2026-11-11)

- Local, **localhost-only** HTML dashboard: per-hit parallel status, live SSE events, decision details, concise disposition drafts, actual timing instrumentation and JSON report export.
- Orchestrator streams completed hits as soon as available; no LLM narration or additional LLM calls for monitoring.
- Read-only imported prior reviewer conclusions are displayed and compared, **never treated as identity proof** and never overwritten.
- Optional OpenAI-compatible `LLMExtractionAdapter` with blank `.env.example`. Offline mode works without configuration. No automatic outbound model call.
- New locally generated synthetic UI preview and short, diagram-first GitHub README.
- Added live HTTP/SSE and model-gating tests; does not implement real BOSS/LN APIs, production authentication or autonomous online research.

# Changelog

## 0.8.0 — Concise disposition and suspected-hit reporting drafts

- Added `ln_agent/disposition.py`: evidence-based, short internal review note and optional unsent compliance report draft.
- Added a real runtime `disposition_reporting` Skill + `disposition_writer` internal Tool, each with README and machine-readable manifest; PolicyGuard validates the output.
- Updated case and hit data contracts with optional application reference, evidence-attributed risk event, and display-only checklist link.
- Added risk-report advice (strong identity, sufficiently suspicious residual evidence, or severe sourced list event with a limited identity lead), separate from the identity classification.
- Added `manual_queue_required=false` by default. Explicit Policy exceptions can enable it; exhausted identity research does not create a generic human queue.
- Kept audit evidence, standalone rule engine, source references, external-approval safeguards, and zero automatic LN writeback or message sending.
- Added two synthetic named scenarios and `python3 -m scripts.run_disposition_demo`.
- Regression: 148 unittest cases passing locally (129 original + 19 added).

**Policy status:** Proposed/advisory only. Actual company approval and source authentication are not implemented.

## v0.8.1 — legal-form and multi-category ingestion

- Isolated legal-suffix normalization to company-name comparison only.
- Added `name_legal_suffix_equivalent` as an auditable soft signal.
- Added evidence references to normalized name matches.
- Parsed comma/semicolon-separated LN risk category labels consistently across
  Risk Gate, PolicyGuard, Suspicion Engine, and Disposition Writer.
- Added 8 synthetic regression tests; no real case data included.
- Source legal characterization remains independent of provider risk labels.
