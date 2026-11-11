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
