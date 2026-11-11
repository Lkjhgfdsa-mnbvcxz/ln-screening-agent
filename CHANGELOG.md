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
