# V0.8 处置输出闭环：简短内部说明 / 疑似命中报告草稿

## 目标

1. **内部填写尽可能短**，优先保存判断结论、核心同一性事实、影响结论的差异、名单事由及必要的不确定性。一般 1–2 句；复杂案件不机械截断信息。
2. **合规沟通不需重新写全文**，仅在达到候选上报规则时拼接工单标识、同一事实、复核请求和已提供的链接。
3. **人不具备额外事实时不进入人工调查队列**：调查价值耗尽可以结束自动调查，但“证据不足”不能自动表示“误报”，也不能代表已授权 LN 关闭。
4. **身份关联判断与风险严重度分离**：强身份证/企业注册号关联可以直接输出疑似真实命中草稿；公司名称一致且事由重大、来源可追踪时可以输出疑似命中草稿，必须保留身份尚未确认的限制。

## 代码映射

- `ln_agent/models.py`：新增 `Hit.risk_event`（`summary` / `severity` / `source_ref` / `material_context[]`）、`Hit.screening_url`、`Case.context.application_ref`；`Decision.disposition` 包含完整输出结构。
- `ln_agent/disposition.py`：确定性 `build_disposition`，由 Router 结束当前命中时调用，不单独发起外部查询。
- `ln_agent/policy_guard.py`：`validate_disposition_draft` 验证 Skill/Tool 机器契约、来源标识、不能自动发送/放行。
- `ln_agent/policy.py`：`reportable_risk_categories`, `reportable_impact_levels`, `report_critical_name_matches`, `mandatory_human_queue_categories` 是**候选策略、未获公司批准**。
- `skills/disposition_reporting/`：`README.md`, `SKILL.md`, `contract.json`。
- `tools/disposition_writer/`：`README.md`, `tool.json`。
- `scripts/run_disposition_demo.py`：两个合成案例一键运行。

## Decision.disposition 主要字段

| 字段 | 实际语义 |
| --- | --- |
| `recommendation` | `EXCLUSION_CANDIDATE`、`SUSPECTED_HIT_REPORT_DRAFT`、`INSUFFICIENT_EVIDENCE_RECORDED`、`UNRESOLVED_EVIDENCE_CHECK`、`TECHNICAL_OR_POLICY_HOLD` |
| `internal_note` | 可以复制到内部审核备注的简洁内容 |
| `compliance_message` | 只有 `report_recommended=true` 时生成；**尚未发送** |
| `source_refs` | 当前判断与名单事由的证据 ID，供第三方进一步追溯 |
| `identity_status` | 身份侧判断，不等于名单风险严重度 |
| `manual_queue_required` | 默认 `false`；仅显式配置的审批例外可变 `true` |
| `compliance_escalation_required_by_policy` | 已配置硬性升级策略是否匹配；与普通建议上报区分 |
| `investigation_complete` | 当前自动检索阶段是否完成；**不等于获准放行** |
| `automatically_sent` / `automatically_cleared` | 永远 `false` |

**历史字段兼容性**：原 `Decision.review_required=true` 和 `Orchestrator.human_approval_required=true` 仍表示“项目没有外部 LN 终态处置权限”，**不表示有新建人工调查队列**。以后若接企业审批系统，建议迁移为 `external_disposition_authorization_required` 以免名称混淆。

## 两套示例（均为虚构）

运行：

```bash
python3 -m scripts.run_disposition_demo
```

**企业示例内部说明：**

> 疑似命中【执法】：企业名称一致，注册地址不一致。事由：合成名单主体被列入某出口管制实体清单。身份关联尚未确认。补充：实际经营地址尚未核实。

**人员示例内部说明：**

> 疑似真实命中【执法】：姓名一致，证件号码一致，出生日期一致，居住地址不一致。事由：合成执法记录涉及涉恐资金调查及财产扣押事项。

合规版本额外显示合成申请编号、对象名称、复核请求和合成复核 URL。

## 严格限制 / 未来工作

- 当前不验证 `risk_event.source_ref` 指向的真实监管原文，只有**带引用的输入信息**；文本用“事由”表示原始 LN 风险记录，`attribution` 中注明未独立核实。**不得**把输入来源 ID 当作真实性证明。
- 不联网、无真实 LN/BOSS/企查查/LLM 接入，不自动发送消息，不自动执行内部系统操作。
- 风险类别、严重程度、阈值未经公司政策批准，所有“上报”都是建议草稿；必须先获授权并用历史真实案例校准才能影响生产审核决定。
- 实际证据绑定、公司更名关系、地址使用时期、全文更正审查、审批权限仍要由现有 FactVerification/RuleEngine/PolicyGuard 提供；文案生成不得提高证据等级。
- 输出为可复制草稿，不得用用户提供的真实客户/证件/内部 BOSS 链接制作公开 Git 示例。

## 验收

- `python3 -m unittest discover -s tests -q`：148 项，其中新增 19 项处置输出测试。
- `python3 run.py inspect`：7 Skills、9 Tool descriptors，新增 Disposition Writer 为 `implemented_internal`。
- `python3 run.py demo`：既有两个合成的排除候选和强关联工单仍可运行。
