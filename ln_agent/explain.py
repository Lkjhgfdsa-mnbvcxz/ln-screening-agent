"""Five inspectable WHY fields for every synthetic hit. No LLM-generated justifications."""
from __future__ import annotations

def build_explanation(*, route: str, reasons: list[str], evidence: dict,
                      gate: dict, actions: list[str], skip_reason: str | None,
                      suspicion: dict | None, investigation_status: str) -> dict:
    excluded = bool(evidence.get("exclusion_rules"))
    linked = bool(evidence.get("linked_rules"))
    return {
      "why_exclusion": "发现排除候选证据（不代表获准放行）：" + ", ".join(evidence.get("exclusion_rules", [])) if excluded else "没有满足候选排除规则的可靠证据",
      "why_continue_or_stop": "route="+route+"; "+ "; ".join(reasons),
      "why_investigation_skipped": "调查已执行："+", ".join(actions) if actions else "无执行查询；原因="+(skip_reason or "已有充分身份判断/未配置外部研究"),
      "why_suspicion": "已运行残余评估；证据充分性="+str((suspicion or {}).get("evidence_sufficiency")) if suspicion is not None else "未进入残余可疑度评估",
      "why_report": ("本地合规升级配置命中，需获授权人员处理" if gate.get("compliance_escalation_required") else "当前未触发已配置的强制合规升级；仍须完成适用的人工复核"),
      "investigation_status": investigation_status,
      "identity_link_signals": evidence.get("linked_rules", []) if linked else [],
    }

def validate_explanation(explanation: dict) -> bool:
    return all(isinstance(explanation.get(k), str) and explanation[k].strip()
               for k in ("why_exclusion", "why_continue_or_stop", "why_investigation_skipped", "why_suspicion", "why_report"))
