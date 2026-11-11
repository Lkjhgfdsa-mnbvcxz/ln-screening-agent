# WorkBuddy 接续开发指令（可直接粘贴给 WorkBuddy）

请以此仓库作为**唯一可运行代码基线**，先执行：

```bash
python3 run_two_cases.py
python3 -m unittest discover -s tests -v
```

**已实跑基线**：120 项测试通过；两个合成工单分别输出 `LINKED_RISK_REVIEW`（强关联，待复核）与 `EXCLUSION_CANDIDATE`（有排除反证，待人工确认）。项目默认只读、模拟数据、无 LN 写回权限。

你之前传给 ChatGPT 的 `workbuddy目前成果.zip` **缺少**你文档描述的完整 `ln_agent/` 源代码，只有 router.py、run.py、两组单测及部分数据和文档。因此最新 router.py 未直接替换此仓库的 router；需要先补齐你的 `ln_agent/rules/ebe.py` 等依赖，逐模块整合并回归测试。不要把完整缺失代码当作“已经在本项目里”。

接下来建议按严格优先级实施（不要重新设计已稳定的 A/B/C 动态路由）：

1. **P0 判断一致性**：将你的 RuleEngine/FieldReliabilityGate 全量实现逐条合并到 `ln_agent/evidence.py` + `ln_agent/rules/registry.py`，保持 `exclusion_evidence_detected` 与 `exclusion_authorized` 分离，完善 case/hit 与证据适用性校验，补优先级交叉、三态权限批准、来源冲突回归。
2. **P0 五检查点正式化**：补全 PolicyGuard 真实可运行的动作白名单、Schema、来源范围、敏感数据控制。对所有会影响判断/行动的 Policy 字段逐一写策略变更测试；元数据字段不必改变业务结论。
3. **P0 崩溃恢复**：目前 `review_store.py` 持久化的是人工核实/结论/REOPEN，**不是**每项外部调查动作的 exactly-once 检查点。新增 `TaskEvent`, `HitState`, 重启幂等续跑、来源级限流、检查点恢复测试。
4. **P1 工单级调度**：多工单隔离、并发预算、原始 LN 命中数完整性、簇类型 SAME_ENTITY/SAME_EVENT/SHARED_SOURCE（仅共享来源资源，不共享结论）。
5. **P1 真实调查适配器**：先获准只读 LN 导出/API；再在明确权限范围内接官方网页、文件采集、企查查；上线前实现 URL SSRF 防护、域名白名单、DNS/redirect 校验、超时/体积限制、文档恶意内容隔离、凭证保护、数据驻留审批。
6. **P1 本地演示**：继续使用 `run_two_cases.py` 两套合成场景，新增对照运行记录、按 Rule ID/Fact/Evidence/HitEvidenceLink 查明每个判断；再构建只读工作台/API（FastAPI 和前端建议单独做）。

**交付标准**：每次迭代必须同时提交代码、测试、`README` 启动方式、通过/失败记录、差异说明；不要让文档宣称的功能超过实际可调用代码。任何真实 LN/商户敏感材料不得进入公开仓库。

> 主体分类：LN Intelligent Screening Agent System（包含 deterministic harness、bounded investigation agent、skills、evidence/rule/policy engines），不是一个单独的 Skill。当前是离线原型，而非自主联网生产 Agent。
