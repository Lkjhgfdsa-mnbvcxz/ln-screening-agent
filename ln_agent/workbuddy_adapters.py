"""Authorized, LOCAL-ONLY WorkBuddy capability adapters.

Two adapters plug into the EXISTING InvestigationAgent -> PolicyGuard ->
Evidence -> RuleRegistry -> RiskGate -> Disposition chain. Neither one opens a
URL, authenticates, writes externally, or decides a screening outcome.

* BrowserSnapshotTool: reads a machine-readable capture bundle that WorkBuddy
  produced by attaching (read-only) to an ALREADY OPEN logged-in BOSS tab.
* LLMCaptureTool: replays an in-session model extraction through the project's
  own LLMExtractionAdapter with a staged, non-network transport. Output always
  goes through validate_extraction(), i.e. model_extracted / checked=False.

The bundle lives in the authorized workstation only. The file shipped in
examples/ is synthetic.
"""
from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from .extraction_contract import SYSTEM_INSTRUCTION
from .llm_adapter import LLMConfig, LLMExtractionAdapter
from .models import Fact
from .policy import Policy

BROWSER_ORIGINS = frozenset({"ln_structured", "official_primary"})
MASK_CHARS = ("*", "x", "X", "•")
IDENTITY_FIELDS = frozenset({"dob", "document_number", "registration_number"})
BROWSER_TOOL = "workbuddy_browser_readonly"
LLM_TOOL = "workbuddy_llm_capture"
CAPTURE_TOOLS = frozenset({BROWSER_TOOL, LLM_TOOL})


class CaptureError(ValueError):
    """Malformed or unsafe staged capture; never silently ignored."""


def authorized_policy(base: Policy | None = None) -> Policy:
    """Explicit opt-in for the two local WorkBuddy tools.

    The default Policy stays offline-only. A run in the authorized environment
    must opt in; no repository example enables these tools implicitly.
    """
    p = base or Policy()
    return replace(p, allowed_tool_names=frozenset(p.allowed_tool_names) | CAPTURE_TOOLS)


class CaptureBundle:
    """Immutable, validated view of a locally staged capture bundle."""

    def __init__(self, records: dict[str, dict], *, metadata: dict | None = None):
        self.records = records
        self.metadata = metadata or {}
        self.lock = threading.Lock()
        self.cache: dict[str, list[Fact]] = {}
        self.read_count = 0

    @classmethod
    def from_json(cls, path: str | Path) -> "CaptureBundle":
        p = Path(path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("records"), dict):
            raise CaptureError("capture bundle requires a records object")
        if raw.get("version") not in {"1.0", 1.0}:
            raise CaptureError("unsupported capture bundle version")
        for key in raw["records"]:
            if not isinstance(key, str) or ":" not in key:
                raise CaptureError("capture key requires a typed prefix")
            if key.split(":", 1)[0] not in {"boss", "model"}:
                raise CaptureError("capture bundle only accepts boss:/model: keys")
        return cls(raw["records"], metadata={k: v for k, v in raw.items() if k != "records"})

    @staticmethod
    def _hit_scope(key: str) -> str:
        parts = key.split(":")
        if len(parts) < 3 or not parts[1] or not parts[2]:
            raise CaptureError(f"capture key must be boss:<case>:<hit>: {key}")
        return f"{parts[1]}:{parts[2]}"

    def browser_facts(self, key: str) -> list[Fact]:
        """Return only facts belonging to THIS hit. Cross-hit facts are rejected."""
        if not key.startswith("boss:"):
            raise CaptureError("browser adapter accepts boss: keys only")
        with self.lock:
            if key in self.cache:
                return list(self.cache[key])
            rec = self.records.get(key)
            if rec is None:
                self.cache[key] = []
                return []
            scope = self._hit_scope(key)
            if not rec.get("source_url") or not rec.get("captured_at"):
                raise CaptureError("browser capture requires source_url and captured_at")
            facts_raw = rec.get("facts")
            if not isinstance(facts_raw, list):
                raise CaptureError("browser capture requires a facts list")
            facts: list[Fact] = []
            for item in facts_raw:
                if not isinstance(item, dict):
                    raise CaptureError("browser fact must be an object")
                if item.get("side") != "hit":
                    raise CaptureError("capture bundle cannot add applicant facts")
                if item.get("origin") not in BROWSER_ORIGINS:
                    raise CaptureError("browser adapter cannot emit model or reviewer facts")
                if item.get("verification_id"):
                    raise CaptureError("browser adapter cannot emit verification ids")
                if not isinstance(item.get("checked"), bool):
                    raise CaptureError("browser fact requires an explicit checked flag")
                if (item.get("field") in IDENTITY_FIELDS
                        and any(ch in str(item.get("value", "")) for ch in MASK_CHARS)):
                    raise CaptureError("masked identity value is not a structured fact")
                eid = str(item.get("evidence_id", ""))
                if not eid.startswith(scope + ":"):
                    raise CaptureError("capture fact evidence_id escapes its own hit scope")
                facts.append(Fact.from_dict(item))
            self.cache[key] = facts
            self.read_count += 1
            return list(facts)

    def model_payload(self, key: str) -> tuple[str, list[dict], str]:
        if not key.startswith("model:"):
            raise CaptureError("model adapter accepts model: keys only")
        rec = self.records.get(key)
        if rec is None:
            return "", [], ""
        excerpt = rec.get("excerpt")
        extractions = rec.get("extractions")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise CaptureError("model capture requires a non-empty excerpt")
        if not isinstance(extractions, list):
            raise CaptureError("model capture requires an extractions list")
        for item in extractions:
            if not isinstance(item, dict) or "field" not in item or "value" not in item:
                raise CaptureError("model extraction entries require field and value")
            if any(k in item for k in ("checked", "origin", "verification_id")):
                raise CaptureError("model extraction must not assert verification state")
        return excerpt, extractions, str(rec.get("source_url", ""))


class BrowserSnapshotTool:
    """Read-only, cached local snapshot adapter. No URL is ever opened here."""

    def __init__(self, bundle: CaptureBundle):
        self.bundle = bundle
        self.read_count = 0
        self.lock = threading.Lock()

    def query(self, key: str) -> list[Fact]:
        with self.lock:
            self.read_count += 1
        return self.bundle.browser_facts(key)


class LLMCaptureTool:
    """In-session model extraction replayed through the project's own adapter.

    `transport` is injected and strictly local: it refuses any request whose
    excerpt or system instruction does not match the staged payload. No HTTP
    request is performed and no external API key is used.
    """

    def __init__(self, bundle: CaptureBundle):
        self.bundle = bundle
        self.read_count = 0
        self.lock = threading.Lock()
        self._local = threading.local()
        cfg = LLMConfig(enabled=True, base_url="http://127.0.0.1/v1",
                        model="workbuddy-session-staged", allow_external=False)
        if not cfg.ready():
            raise CaptureError("staged LLM configuration is invalid")
        self.adapter = LLMExtractionAdapter(cfg, transport=self._transport)

    def _transport(self, body: dict) -> dict:
        messages = body.get("messages") or []
        if len(messages) != 2 or messages[0].get("content") != SYSTEM_INSTRUCTION:
            raise CaptureError("staged transport requires the project's system instruction")
        excerpt = messages[1].get("content")
        payload = getattr(self._local, "payload", None)
        if payload is None or excerpt != getattr(self._local, "excerpt", None):
            raise CaptureError("staged transport mismatch: refusing to invent model output")
        return {"choices": [{"message": {
            "content": json.dumps(payload, ensure_ascii=False)}}]}

    def query(self, key: str) -> list[Fact]:
        excerpt, extractions, source_url = self.bundle.model_payload(key)
        with self.lock:
            self.read_count += 1
        if not excerpt:
            return []
        self._local.excerpt = excerpt
        self._local.payload = extractions
        try:
            return self.adapter.extract_candidates(
                excerpt, evidence_id=f"{key}:candidate",
                source_url=source_url, allow_external_text=True)
        finally:
            self._local.payload = None
            self._local.excerpt = None


def build_capture_tools(bundle: CaptureBundle) -> dict[str, Any]:
    return {BROWSER_TOOL: BrowserSnapshotTool(bundle),
            LLM_TOOL: LLMCaptureTool(bundle)}
