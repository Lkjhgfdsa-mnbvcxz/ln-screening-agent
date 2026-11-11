# Disposition Writer Tool｜内部短句与合规沟通草稿

**状态：`implemented_internal`。** 本地确定性 Python 代码，非联网或自动发消息工具。

- 实际入口：`ln_agent.disposition.build_disposition`。
- 输入：当前 Case、Subject、Hit、EBE EvidenceResult、Router route、RSA、Policy、RiskGate、来源 Fact/Evidence IDs。
- 输出：`Decision.disposition`，含 `internal_note`、`compliance_message`、`report_recommended`、`source_refs`、`manual_queue_required`、`automatically_sent` 等。
- 防护：仅引用带 `source_ref` 的名单事由；没有来源不能编造事实；多段文本输入统一单行归一；自动发送和自动放行被 PolicyGuard 拒绝。
- 权限：**不访问网页、不提交 BOSS、不操作 LN、不进入接受名单、不自动通知合规。**
- 运行方式：`python3 -m scripts.run_disposition_demo`。可查看两个合成场景的实际生成结果。

相关 [Skill](../../skills/disposition_reporting/README.md) · [Tool 注册表](../README.md)
