# 合并评估报告 | 2026-11-11

## 实际收到的文件

上传的 WorkBuddy ZIP 提供：新版 router.py、run.py、test_rule_engine.py、test_round1_regression.py、document_fixtures.json、report.json、README.md、总体设计 V1.0/V1.1 及 V0.2 评审文档。

**未提供**：README 所描述的 `ln_agent/rules/ebe.py`、完整 `ln_agent/models.py`、新版 `policy.py`、新版 `policy_guard.py`、`risk_gate.py`、`explain.py`、`document_intelligence` 树、`examples/demo_case.json` 等运行时依赖。因此，该 ZIP 无法独立复现其声称的 111 项测试，旧 `router.py` 无法直接替换 V0.5。

## 本次真实落地的合并内容

| 源 | 继承与整合 | 在代码里可以检查什么 |
|---|---|---|
| 我方 V0.5 | 动态路由、证据判断、文档读取与溯源、核实门槛、多来源佐证、SQLite 审核历史与 REOPEN | 原有 `tests/` 108 项继续通过 |
| WorkBuddy 设计及实装入口 | 候选规则 P01–P10 六要素清单 | `ln_agent/rules/registry.py` / `Decision.rule_findings` |
| WorkBuddy 评审 | `Gate Q0 + final`，身份核验与合规上报分离 | `ln_agent/risk_gate.py` / `Decision.gate` / 集成交叉测试 |
| WorkBuddy 评审 | 执行期 Policy/Skill 限制，非提示词 | `PolicyGuard.check_ingest`, `check_tool_call`, `validate_facts`, `validate_hard_rules`, `check_state_transition` |
| WorkBuddy 评审 | 五类 Why 和动态路径 | `Decision.explanation`, `execution_path`, `stop_reason`, `version_snapshot` |
| WorkBuddy 评审 | 禁用规则要真实改变结果 | `Policy.disabled_rules`; `test_disable_dob_rule_changes_runtime` |
| V0.5 + 增量 | `extraction_verified=False` / `content_verified=False` 的证据不能用于硬判 | `evidence.eligible_for_hard` + 2 项交叉测试 |

**明确没有完成的合并**：WorkBuddy 新版 Router 的全部细节与全部 34 个 Policy 字段；其缺失的规则实现；完整六步 FieldReliabilityGate；完整命中级检查点和崩溃恢复；真实来源独立鉴真和人工登录。当前新增的 Registry 是可运行的候选规则层，其完整 10 项元数据并不代表 10 项独立判断都已获得公司批准或业务验收。RuleRegistry 内 P05/P07/P10 部分检测能力仍属于初步/待扩展。

## 实测

- `python3 -m unittest discover -s tests -q`：**Ran 120 tests / OK**。
- `python3 run_two_cases.py`：两份独立合成工单均完成，分别输出 `LINKED_RISK_REVIEW` 与 `EXCLUSION_CANDIDATE`，均 `review_required=true`、`exclusion_authorized=false`。
- 制裁警报 + 生日冲突：Q0 与 final 均保留人工筛查复核；若**仅在测试中**配置该类别强制升级，升级标志保留，不会被排除候选消除。
- 禁用 P02 出生日期规则：原排除候选路径发生变化，证明策略确实影响运行结果。
- 对证据显式标记提取错误或内容错误：不触发硬生日排除。

## 一项必须先经公司确认的政策边界

- `requires_manual_screening_review`：保留 LN 警报的人工审核流程。
- `compliance_escalation_required`：只由明确配置的类别触发；当前默认类别为空，非正式企业制度结论。
- `exclusion_evidence_detected`：判断引擎找到候选排除证据。
- `exclusion_authorized`：默认不可自动结案/加白名单。**即使身份匹配/冲突很强，也不代表得到合规处置权限。**

## 风险与限制

这是一套离线合成数据的原型，不是具有实际权限的 LN Agent；“证据已核实”在演示中仅表示输入被标记并通过对应的模拟审核账本，不能代替正式来源真实性或个人关联证明。实际商户须经人工及适用公司审批。
