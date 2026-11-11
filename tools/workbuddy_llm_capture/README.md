# workbuddy_llm_capture

**状态：`implemented_authorized_local`（本地 staged transport，零外部 API 调用）**

把 WorkBuddy 会话内大模型的结构化抽取能力接入 `InvestigationAgent`，但**不把任何判断权交给模型**。

## 实际做了什么

1. WorkBuddy 会话内模型按项目 `extraction_contract.SYSTEM_INSTRUCTION` 从页面可见的 LN 档案文本中抽取**明确陈述的可核验事实**，结果暂存本地 capture bundle。
2. `LLMCaptureTool.query("model:<case>")` 把这段文本和抽取结果交给项目自带的 `LLMExtractionAdapter`，通过注入的 `transport` 返回 staged 结果（**不发出任何网络请求**）。
3. `LLMExtractionAdapter` 原样执行 `validate_extraction()`：强制 `origin=model_extracted`、`checked=False`、`verification_id=""`、`extraction_verified/content_verified=None`。
4. 这些事实只能作为候选进入 `evidence.evaluate()`；`eligible_for_hard()` 要求 `checked=True` 且来源可信，因此模型事实**永远无法单独触发** `DOB_EXACT_MATCH` / `DOB_EXACT_CONFLICT` / `DOCUMENT_EXACT_MATCH` 等硬规则。

## 不能绕过什么

- `PolicyGuard.validate_facts` 读取本 manifest 的 `allowed_fact_origins=["model_extracted"]` 与 `facts_must_be_unchecked=true`：模型事实若被篡改成 `checked=True` 或 `reviewer_verified`，直接抛 `PolicyViolation`，整条命中进入 `POLICY_BLOCKED_REVIEW`。
- 模型**不输出**误报 / 命中 / 上报决定，也不生成审核说明；业务结论只由 `build_disposition` 依据确定性规则产出。
- 路由、工具预算、风险闸门、处置草稿校验全部保持原有实现。
- 默认 `Policy.allowed_tool_names` 不含此工具；仅授权本地运行显式开启。

> 与 `tools/llm_extraction/`（OpenAI-compatible 远端接口，`optional_not_connected`）是两个不同工具：本工具走会话内模型 + 本地暂存，不需要 API Key，也不把内部文本发到外部端点。
