# workbuddy_capture（辅助 Skill）

面向开发/审核人员的说明：这是**辅助采集契约**，不是审批制度，也不是可独立运行的 AI 子代理。

- `contract.json`：运行时机器契约（触发前缀、允许的 Tool、禁止捷径）。由 `ln_agent/skill_catalog.py` 加载。
- `SKILL.md`：核验方法与领域边界，供人和 Agent 阅读；**不授予权限**。
- 真正的权限在 `Policy.allowed_tool_names`、`PolicyGuard.check_tool_call()`、`tools/*/tool.json` 的 `status` / `allowed_prefixes` / `allowed_fact_origins` 中执行。

调用链：`select_skills()` 加载契约 → `DecisionRouter` 解析 `boss:` / `model:` → `PolicyGuard` 校验工具与预算 → `InvestigationAgent` 调用授权 Tool → `validate_facts()` → Rule Engine + RiskGate → `build_disposition()`。

运行 `python3 run.py inspect` 可查看已注册 Skill 与 Tool 状态；`python3 -m unittest discover -s tests -v` 包含绕过防护的回归测试。
