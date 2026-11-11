# WorkBuddy 授权本地采集（辅助 Skill）

**ID:** `SKILL_WORKBUDDY_CAPTURE_V1` · **状态：** 运行时生效的辅助契约，不授予任何审批权限

## 适用

当命中的 `research_keys` 含 `boss:` / `model:` 前缀时，由 `skill_catalog.select_skills()` 与主 Skill 一起加载。它**不替代** `person_ln` / `company_ln` / `address_ln`，也不改变查询优先级和路由顺序。

## 方法与输出

| 前缀 | 授权 Tool | 输出 |
| --- | --- | --- |
| `boss:` | `workbuddy_browser_readonly` | 已登录页面只读提取的 LN 结构化事实，带 `evidence_id`、来源 URL、采集时间 |
| `model:` | `workbuddy_llm_capture` | 会话内模型按 `SYSTEM_INSTRUCTION` 抽取的**未核实**候选事实 |

两类事实都经 `PolicyGuard.validate_facts` 校验后才进入 `evidence.evaluate()`。所有调用都产生真实的 `TOOL_STARTED` / `TOOL_FINISHED` 事件与单调耗时。

## 禁止捷径

- 不得把模型抽取结果当作已核实事实，或把 `checked` 改成 `true`。
- 不得把脱敏号码（`*`、`x`、`X`、`•`）当作完整证件号、完整生日或注册号。
- 不得由模型输出误报 / 命中 / 上报决定，也不得让模型生成审核说明。
- 不得把历史人工审核结论注入规则引擎事实（历史记录只在 `workbench/prior.py` 中展示与对照）。
- 不得因信息不足自动创建人工调查队列；`manual_queue_required` 只能来自显式配置的策略例外。

## 关键边界

模型产出的 `model_extracted / checked=false` 事实不满足 `eligible_for_hard()`，因此**不能**触发任何硬排除或强关联规则。只有项目自带的 `FactVerifier` 配合人工 attestation 才能把文档候选升级为 `reviewer_verified`。本 Skill 没有这个能力，也不得绕过。
