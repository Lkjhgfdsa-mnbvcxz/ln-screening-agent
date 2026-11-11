# LN Intelligent Screening Agent — Integrated MVP (offline)

**Version:** `integration-2026-11-11` · Python 3.10+ · **synthetic-data / read-only / human-review-only**

This runnable project merges the **complete V0.5 implementation** (dynamic routing, document parsing, contextual evidence extraction, fact verification, independent-source corroboration, SQLite review history and REOPEN) with the **implementable portions of WorkBuddy Round 2** (runtime P01–P10 rule registry, independent risk gate, explicit guard checkpoints, five-WHY explanation and cross-condition tests).

> **This is a prototype of an Agent system / harness, not a production compliance tool or an autonomous LN decision-maker.** The offline `InvestigationAgent` uses local synthetic fixtures, not an LLM, sanctioned lists, public search, authentic LN/BOSS systems or QCC APIs. A rule candidate is **not a company-approved screening rule**. No automatic whitelist, LN disposition or compliance report is implemented. Never use generated decisions to accept real merchants.

## 1. Quickest reproducible demonstration (one linked and one false-positive candidate)

```bash
# unzip this folder, open terminal, cd to the folder containing this README
python3 run_two_cases.py
```

Expected console summary:

```text
strong_link: LINKED_RISK_REVIEW | identity=strong_link | manual_review=True | authorized_exclusion=False
false_positive: EXCLUSION_CANDIDATE | identity=excluded_candidate | manual_review=True | authorized_exclusion=False
PASS: both independent synthetic cases
```

Output `examples/two_case_demo_report.json` shows each input, route, facts, P01–P10 findings, Risk Gate conditions, five reasons, execution path and disposition safeguards.

**Interpretation:** “linked” is a reliable *candidate identity association* requiring risk review, **not** approval of the merchant or verified guilt. “false positive” is an evidence-backed *exclusion candidate* requiring manual confirmation, **not** an automatically authorized clearance.

## 2. Automated tests

```bash
python3 -m unittest discover -s tests -v
```

**120 tests passed** in the integration environment: 108 pre-existing V0.5 cases and 12 integration tests. These are offline *functional tests*, not measured regulatory accuracy or precision/recall against labeled LN cases. GitHub Actions also runs them on push/PR.

## 3. Other runnable scenarios

```bash
python3 run.py examples/demo_case.json --research examples/research_fixtures.json --out examples/legacy_demo_report.json
python3 run_documents.py examples/document_case.json examples/document_manifest.json --out examples/document_demo_report.json
python3 run_verification_demo.py
python3 run_v05_demo.py
```

For PDF/XLSX parsing, optional third-party packages can be installed using `python3 -m pip install -r requirements-optional.txt`. TXT/HTML routes and all 120 tests run with the standard library; document fixtures do not imply authenticated external retrieval.

## 4. Actual code path

```text
Case (synthetic JSON)
  -> Orchestrator (per-hit isolation and concurrent execution)
    -> PolicyGuard ingestion check (case + hit + allowed facts)
    -> DecisionRouter
        -> RiskGate Q0 (screening review vs separately configured compliance escalation)
        -> evidence.evaluate (existing deterministic comparisons)
        -> rules.RuleRegistry (P01–P10 findings + runtime disable switch)
        -> PolicyGuard hard-rule check
        -> either:
           - exclusion candidate (never auto-clear),
           - strong linked identity for risk review,
           - InvestigationAgent (bounded read-only fixture / Document Intelligence),
           - FactVerifier (human attestation fixture; cannot self-certify),
           - corroboration (distinct confirmed source lineages),
           - SuspicionAgent (only unresolved and no further action)
        -> RiskGate FINAL check + five-WHY explanation
  -> optional ReviewStore SQLite audit + REOPEN
  -> JSON report for a HUMAN reviewer
```

### Source code map

| Folder/file | Responsibility |
| --- | --- |
| `ln_agent/models.py` | `Case`, `Subject`, `Hit`, `Fact` and `Decision`; provenance metadata |
| `ln_agent/evidence.py` | Deterministic comparisons, validity/compatibility, temporal impossibility |
| `ln_agent/rules/registry.py` | WorkBuddy-inspired P01–P10 specifications, current findings, runtime rule enable/disable |
| `ln_agent/policy_guard.py` | Ingestion, source/skill tool allowlist, candidate fact validation, hard-rule restriction, unsupported disposition blocking |
| `ln_agent/risk_gate.py` | Independent Q0/final gate; history retention; screening alert vs compliance escalation |
| `ln_agent/router.py` | Per-hit dynamic decision loop; evidence re-evaluation; early stop; skip and tool failure |
| `ln_agent/explain.py` | Five reasons tied to actual runtime state, not generated prose |
| `ln_agent/tools.py`, `ln_agent/document_tools.py` | Fixture research and document adapters; no external requests |
| `ln_agent/document_intelligence/` | Local parsing, text targeting, contexts, material sweep, provenance |
| `ln_agent/fact_verification.py` | Check exact original location and simulated human attestation before using extracted facts |
| `ln_agent/corroboration.py` | Source lineage independence and contradiction handling |
| `ln_agent/review_store.py`, `ln_agent/review_service.py` | SQLite review persistence, revisions, REOPEN and local audit history |
| `tests/` | Regression and cross-condition safety tests |
| `examples/` | **Synthetic** cases and fixture documents |

## 5. Integration boundaries and differences

The WorkBuddy upload **did not contain its complete `ln_agent/` runtime package**. It contained only a newer `router.py`, `run.py`, two test modules, a fixture, a pre-generated report and design documents. That `router.py` imports unavailable `ln_agent.rules.ebe`, `ln_agent.explain`, `ln_agent.risk_gate`, and other interfaces whose exact implementation was not supplied. Replacing V0.5's router with it would break the runnable code.

This integrated runtime instead **ports the principles into V0.5's actual interfaces**, with tests proving rule disable, gate persistence, evidence provenance and five explanations. The WorkBuddy `111 tests` claim was **not independently reproduced** from the incomplete upload. See `docs/WORKBUDDY_HANDOFF.md` and `docs/INTEGRATION_ASSESSMENT.md` for remaining differences.

## 6. Security + Git

See `docs/GIT_HANDOFF.md` before pushing. Public repos should use **synthetic data only**, as here. Do **not** add internal SOP screenshots, real merchant details, sanctions results, identity photos, cookies, auth tokens, system URLs, or employee private records. Use a private company-approved repository if the project itself or its business logic is proprietary.

This project has no deployment/API credentials and no production web interface. `requirements-optional.txt` is only for local document parsing. No automatic writes to LN or whitelist operations are implemented.
