# Agent development handoff

This repository is an OFFLINE, synthetic-data-only LN screening Agent Harness prototype.

Read `README.md`, `agents/README.md`, `skills/README.md`, `tools/README.md`, and `docs/WORKBUDDY_HANDOFF.md` before coding.

**Project contract**

- Preserve `Rule Engine -> PolicyGuard -> Decision Router` evidence-driven behavior and the independent Risk Gate.
- Tool and Skill access is governed by `ln_agent/tool_catalog.py`, `ln_agent/skill_catalog.py` and `PolicyGuard`; never bypass these with a free-form model tool call.
- `skills/*/contract.json` is executable configuration. `SKILL.md` provides operator/agent guidance and must not grant permissions.
- `tools/*/tool.json` records actual connectivity; `not_connected` must remain unavailable until explicitly implemented and authorized.
- Do not treat `model_extracted` as human-verified; all hard decisions need traceable evidence and applicable verification.
- Do not auto-approve merchants, write back to LN, whitelist hits, or send sensitive case data to outside services.
- Add regression tests with each change. Run `python3 run.py inspect`, `python3 run.py demo`, and `python3 -m unittest discover -s tests -v`.

**Disposition drafting contract (V0.8)**

- Each `Decision.disposition` has a **concise Chinese internal note** and a traceable `source_refs` list; reportable cases additionally have an **unsent** compliance message.
- An insufficient-evidence case without actionable leads must not be pushed to a generic human investigation queue. Human queue exceptions require explicit configured policy; a suspected-hit report to compliance is a different action.
- Report recommendation uses candidate risk policies (not company-approved). Evidence of severe risk requires an explicit source reference; do not claim independent verification of LN events just because a record includes a citation.
- Never auto-send to Feishu/IM/email or BOSS/LN. Existing legacy `review_required=true` only means external final disposition would need authorization, **not** that a human research queue is created.
- Run `python3 -m scripts.run_disposition_demo` and the new disposition tests after changes; actual business criteria require approval.

**Next engineering tasks**: authenticated read-only source adapters (pending approval), authoritative Policy versioning, proper per-action persistent checkpoints and retries, sandboxed URL/document ingestion, actual bounded LLM Investigation agent, user-authorized final review UI.

No real merchant/customer data or credentials should be committed.

## Local web workbench (v0.9)

- Start `python3 run.py web`, open `http://127.0.0.1:8765`; keep it localhost-only until there is real authentication.
- Observe actual per-hit events in `ln_agent/workbench/runner.py` and `router.py`; do not add LLM narration calls merely to track actions.
- Historical decisions are **imported workflow records**, not identity evidence. `ln_agent/workbench/prior.py` must not turn them into verified facts or silently overwrite past reviewers.
- Optional LLM interface is `ln_agent/llm_adapter.py`, disabled by default and never invoked by offline runs; external data transfer requires explicit consent.
- For new tools, emit `TOOL_STARTED`/`TOOL_FINISHED` with actual monotonic durations; keep `Tool` manifests and Skill contracts in sync.
- Run web/SSE integration tests in `tests/test_workbench.py`; keep the GitHub README brief and illustration-based.

## Authorized local WorkBuddy adapters (v0.9.3)

- `workbuddy_browser_readonly` / `workbuddy_llm_capture` are `implemented_authorized_local` and **never** in the default `Policy.allowed_tool_names`; opt in with `authorized_policy()` only in an authorized local run.
- Tool resolution is a prefix lookup in `ln_agent/tool_catalog.py`; do not reintroduce a hardcoded tool branch or a free-form model tool call in the Router.
- `PolicyGuard.validate_facts()` enforces each tool manifest's `allowed_fact_origins` / `facts_must_be_unchecked`. Keep these fields in sync when adding a tool, and add a regression test that tries to smuggle `checked=true` model facts.
- A capture bundle is scoped per hit (`boss:<case>:<hit>`); cross-hit evidence, masked identity values and `verification_id` must be rejected. Real bundles and full event logs stay in the authorized environment; only synthetic bundles belong in this repository.
- See `docs/WORKBUDDY_INTEGRATION.md` for the exact call chain and the connected / not-connected list.

## Public synthetic replay (v0.9.3)

- `scripts/build_replay.py` is the **only** publisher of execution data. It reads just `examples/case_workbuddy_capture.json` and `examples/workbuddy_capture_bundle.json`, runs the real engine, and writes `examples/workbuddy_capture_replay.json`, `replay.html` and `index.html`.
- Never point the generator, the workbench, or a test at an authorized local capture directory or any other real-data path. Real bundles, structured DOM captures and full JSONL logs stay outside the repository.
- Keep `_assert_synthetic()` and `tests/test_public_replay.py` intact; they are the publication guard. Only aggregate, non-business counters may appear in public pages.
- `replay.html` must stay a single self-contained file with no external resources, so it works both on GitHub Pages (site source `/`) and from a downloaded `file://` copy. Keep relative links root-based.
- Changing the engine's emitted events requires regenerating the replay and updating the test count passed via `--tests`.
