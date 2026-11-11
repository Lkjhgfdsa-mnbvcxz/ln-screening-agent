"""Typed tool registry: offline tools callable; real external connectors disabled."""
from __future__ import annotations
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1] / "tools"
KNOWN = ("fixture_research", "document_intelligence", "fact_verification", "source_corroboration",
         "ln_readonly", "official_web", "qcc", "company_registry", "disposition_writer",
         "llm_extraction", "workbuddy_browser_readonly", "workbuddy_llm_capture")

# `implemented_authorized_local` is still LOCAL-ONLY: the adapter reads a staged
# capture bundle from the authorized workstation. It never opens a URL itself.
CALLABLE_STATUSES = frozenset({"implemented_offline", "implemented_authorized_local"})

# Source-key prefix -> registered tool. This is a lookup table only: the
# Decision Router's check -> start -> facts -> re-evaluate flow is unchanged.
_PREFIX_TOOL = {
    "doc": "document_intelligence",
    "boss": "workbuddy_browser_readonly",
    "model": "workbuddy_llm_capture",
}
DEFAULT_TOOL = "fixture_research"


def tool_for_source_key(source_key: str) -> str:
    if ":" not in source_key:
        raise ValueError("research action needs typed source prefix")
    return _PREFIX_TOOL.get(source_key.split(":", 1)[0], DEFAULT_TOOL)


def load_tool(tool_id: str, *, root: Path | None = None) -> dict:
    if tool_id not in KNOWN:
        raise ValueError("tool not registered: " + tool_id)
    base = root if root is not None else ROOT
    obj = json.loads((base / tool_id / "tool.json").read_text(encoding="utf-8"))
    if obj.get("id") != tool_id or obj.get("writes_external") is not False or not obj.get("read_only"):
        raise ValueError("unsafe/malformed tool contract: " + tool_id)
    return obj


def available_for_call(tool_id: str, *, source_key: str | None = None) -> tuple[bool, str]:
    spec = load_tool(tool_id)
    if spec["status"] not in CALLABLE_STATUSES:
        return False, f"tool unavailable: {spec['status']}"
    if spec["status"] == "implemented_authorized_local":
        if spec.get("local_only") is not True or not spec.get("authorization"):
            return False, "authorized local tool missing local_only/authorization manifest fields"
        if spec.get("network"):
            return False, "authorized local tool must not declare network access"
    if source_key is not None:
        prefix = source_key.split(":", 1)[0]
        if prefix not in spec["allowed_prefixes"]:
            return False, f"source prefix {prefix!r} not allowed for {tool_id}"
    return True, ""


def tool_status() -> dict[str, str]:
    return {k: load_tool(k)["status"] for k in KNOWN}
