# LLM extraction (optional)

**Status:** Disabled until configured. The local workbench runs without any LLM key.

- Code: [`ln_agent/llm_adapter.py`](../../ln_agent/llm_adapter.py)
- Contract: `tool.json`
- Interface: `LLMExtractionAdapter.extract_candidates(excerpt, evidence_id, source_url, allow_external_text=True)`
- Input: explicitly approved document excerpt; **never automatically send real KYB or internal BOSS content**
- Output: structured **unverified** `Fact[]`; hard identity rules cannot trust these until an independent verification path approves them
- Guardrails: explicit enablement, URL scheme constraints, request size/time bounds, no redirects, no automatic LN writeback

## Configuration

Copy `.env.example` to `.env`, set `LN_LLM_ENABLED=true`, `LN_LLM_BASE_URL`, `LN_LLM_MODEL`, and if needed `LN_LLM_API_KEY`. For external HTTPS, also set `LN_LLM_ALLOW_EXTERNAL=true`. Do not commit `.env`.

Check without calling the model: `python3 run.py llm-status`.

**Important:** The ordinary `run.py demo` and `run.py web` flows never invoke an LLM. WorkBuddy can add a policy-authorized extraction call when the real data-source boundary is implemented. A configured endpoint is not automatic permission to transmit private files.
