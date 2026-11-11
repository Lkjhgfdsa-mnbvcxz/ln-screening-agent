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
