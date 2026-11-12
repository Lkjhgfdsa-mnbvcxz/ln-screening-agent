# WorkBuddy 能力接入说明（v0.9.3）

本文说明**在既有审核流程内**接入 WorkBuddy 的浏览器只读读取、数据读取与会话内大模型，范围与未接通项均如实列出。

## 设计原则

- 不新增审核阶段，不改动 `Rule Engine → PolicyGuard → Decision Router → Risk Gate → Disposition` 的职责划分。
- 不把路由判断、排除/命中结论、上报决定交给模型。
- 所有能力都通过 `skills/*/contract.json` + `tools/*/tool.json` 注册，并由 `PolicyGuard.check_tool_call()` 在运行时校验。
- `SKILL.md` 只提供方法指导；真正的拦截在 Python 代码和机器契约里。

## 接入点

| 能力 | WorkBuddy 侧 | 项目侧入口 | 事实形态 |
| --- | --- | --- | --- |
| 已登录浏览器只读读取 | attach 已打开标签、读 DOM 文本；不新建标签/不导航/不刷新/不提交 | `BrowserSnapshotTool.query("boss:<case>:<hit>")` | `ln_structured` / `official_primary`，可 `checked=true`；脱敏值拒绝入库 |
| 结构化数据读取 | 把页面表格按列解析成带 `evidence_id` 的记录，本地暂存 capture bundle | `CaptureBundle` | 每条事实绑定本命中的 scope，跨命中证据直接拒绝 |
| 会话内大模型 | 按 `extraction_contract.SYSTEM_INSTRUCTION` 抽取明确陈述的事实 | `LLMCaptureTool.query("model:<case>:<hit>")` → `LLMExtractionAdapter` + 注入的 staged transport | 恒为 `model_extracted / checked=false`，零外部 API 调用 |

`staged transport` 严格校验请求中的 system instruction 与 excerpt 必须和本地暂存包一致，否则抛错；它不发起任何 HTTP 请求。项目自带的远端 OpenAI-compatible 接口（`tools/llm_extraction/`）保持 `optional_not_connected`，两者互不替代。

## 调用链（与离线 fixture 完全相同）

```
select_skills(entity_type, research_keys)          # 加载主 Skill + workbuddy_capture
  -> DecisionRouter: ordered_queries / remaining
  -> tool_for_source_key(key)                     # 前缀 -> 注册表查表
  -> PolicyGuard.check_tool_call(...)             # Policy 白名单 + tool.json 状态/前缀 + Skill 契约 + 预算
  -> TOOL_STARTED / TOOL_FINISHED（真实单调耗时）
  -> InvestigationAgent 调用对应本地 adapter
  -> PolicyGuard.validate_facts(..., tool_name)   # manifest 驱动 origin / checked 围栏
  -> FACTS_RECEIVED
  -> evidence.evaluate + RuleRegistry + RiskGate  # 重新判断，路由不变
  -> build_disposition + validate_disposition_draft
```

## 为什么模型不能编造审核依据

1. `LLMExtractionAdapter` 的 `validate_extraction()` 强制 `origin=model_extracted`、`checked=false`、`verification_id=""`、`extraction_verified/content_verified=None`。
2. `evidence.eligible_for_hard()` 要求 `checked=True` 且来源可信，模型事实**永远**不满足，因此无法触发 `DOB_EXACT_MATCH` / `DOB_EXACT_CONFLICT` / `DOCUMENT_EXACT_MATCH` / `PRE_BIRTH_ACTION_IMPOSSIBLE`。
3. `PolicyGuard.validate_facts()` 读取 `tool.json` 的 `allowed_fact_origins` 与 `facts_must_be_unchecked`：若把模型事实伪装成 `ln_structured` 或 `checked=true`，抛 `PolicyViolation`，命中进入 `POLICY_BLOCKED_REVIEW`。
4. 业务结论只由 `build_disposition()` 依据确定性证据产生，`validate_disposition_draft()` 再校验结论标签、状态、来源与「不得自动发送」。
5. 浏览器采集包同样受围栏约束：不能提交 `reviewer_verified`、`verification_id`、跨命中证据或脱敏身份值。

## 启用方式与边界

默认 `Policy.allowed_tool_names` **不含**这两个工具，`python3 run.py demo` / 其他合成案例完全不受影响。授权本地运行需显式：

```python
from ln_agent.workbuddy_adapters import (CaptureBundle, authorized_policy, build_capture_tools)
bundle = CaptureBundle.from_json("/authorized/local/bundle.json")
report = Orchestrator(authorized_policy(), FixtureResearchTool({}),
                      extra_tools=build_capture_tools(bundle)).run(case, on_event=...)
```

- 真实 capture bundle、完整事件日志和真实业务数据**只保存在授权环境**，不进入公开仓库。
- 公开仓库中的 `examples/workbuddy_capture_bundle.json` 是纯合成数据，用于回归测试与可交互回放。
- 不因证据不足自动创建人工调查队列：`manual_queue_required` 仍只来自显式配置的策略例外，默认恒为 `false`。
- 未接通：真实 LN/BOSS API、企查查、官方登记处在线接口、生产身份认证、自动审批、写回、外部消息发送、长期任务断点恢复。

## 公开合成回放

[`../replay.html`](../replay.html) 用同一条调用链演示上述两个适配器：把 `examples/case_workbuddy_capture.json` 交给真实引擎执行一次，将实际发出的 68 个事件嵌入单文件静态页。事件不是手写脚本，回放中可以直接看到 `SKILL_SELECTED → POLICY_CHECK → GATE_CHECK → TOOL_AUTHORIZED → TOOL_STARTED / TOOL_FINISHED → FACTS_RECEIVED → RULE_EVALUATED → HIT_RESULT_READY`。

`scripts/build_replay.py` 在生成前会执行 `_assert_synthetic()`：拒绝真实工单号、内部域名、凭据、证件号长度数字、非 `synthetic://` 来源以及任何自动发送/放行标记。`tests/test_public_replay.py` 另外验证公开页不加载外部资源、嵌入数据与 JSON 一致、模型事实仍为 unchecked、事件流可由引擎复现。

## 验证

```bash
python3 run.py inspect                       # 8 Skills / 12 Tool 描述
python3 run.py web                           # 选择「WorkBuddy 本地采集 · 合成回放」
python3 scripts/build_replay.py --tests 242  # 重新生成静态回放
python3 scripts/check_sensitive.py           # 全仓 + 全历史发布闸门
python3 -m unittest discover -s tests -v    # 242 项，含 16 项接入与绕过防护回归测试
```

## v0.9.6 补充：最终指标不在这条判定链上

`final_indicator` 是在 `build_disposition()` 完成业务结论之后才派生的**下游统计指标**，不调用任何 adapter、不产生 `Fact`、不经过 `validate_facts()`，也不改变 `recommendation` / `business_conclusion` / `report`。因此它既不会绕过上述五道防护，也不能被模型用来编造审核依据。规则、围栏与「基于项目 + 修复项目缺陷」的清单见 [`FINAL_INDICATOR.md`](FINAL_INDICATOR.md)。
