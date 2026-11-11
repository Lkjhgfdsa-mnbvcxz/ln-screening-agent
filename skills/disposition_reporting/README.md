# Disposition Reporting｜审核结论与合规上报草稿

本 Skill 是主调度器的**处置输出能力**，不是新建的 LLM Sub-agent。它读取现有证据和判断结果，不主动查网、不会写回 LN。

## 触发条件
每条命中从 Router 得到当前判断后生成内部短句。只有当政策明确要求升级、身份强关联，或具备来源标识的严重风险且达到候选上报条件时，才生成 `compliance_message`。

## 输出

- `internal_note`：简洁内部填写文本；一般 1–2 句，涉及重要矛盾允许稍长。
- `compliance_message`：**仅当 `report_recommended=true`**，包含工单标识、同一套核心事实、复核请求和可选链接。
- `recommendation`：排除候选 / 疑似命中上报草稿 / 证据不足记录 / 来源待核验 / 技术阻断。
- `source_refs`：关键比较事实和风险事由的来源 ID。只提供来源 ID 不等于已完成独立鉴真。
- `manual_queue_required`：默认 false；仅公司批准的明确例外配置可开启。
- `automatically_sent=false`，`automatically_cleared=false`：始终受限。

## 实际代码

- 生成器：[`../../ln_agent/disposition.py`](../../ln_agent/disposition.py)
- 输出防护：[`../../ln_agent/policy_guard.py`](../../ln_agent/policy_guard.py)
- 机器契约：[`contract.json`](contract.json)
- 调查/证据判断仍在 Router + EBE + RSA。此 Skill **无权**自行判定身份或直接上报。

## 运行

```bash
python3 -m scripts.run_disposition_demo
python3 -m unittest discover -s tests -v
```

目前只有**合成离线数据**。候选上报权重和风险阈值未获得公司批准，不可直接用于生产自动处置。

> V0.9.2：新增 `business_conclusion`（未命中 / 疑似命中 / 命中或 null）和 `business_conclusion_status`。旧 `recommendation` 继续保留为内部技术状态，不在业务结果区直接展示。
