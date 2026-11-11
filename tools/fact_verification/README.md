# 事实核实与人工审阅记录 · README

> **Tool ID:** `fact_verification` · **当前状态:** `implemented_internal` · **可执行：内部受信任流程**（非 Sub-agent 任意外调）

## 功能

验证文档片段的原文、哈希、页面位置、事件含义、人物对应关系及经授权的模拟人工确认。

## 运行入口与调用权限

`FactVerifier.verify_packet(...)`，实现 `ln_agent/fact_verification.py`；**仅 Orchestrator/受信任执行层使用**。

- `network`: `false`
- `writes_external`: `false`
- `read_only`: `true`
- source key 前缀：不按 research key 直接调用

**权限约束：** `tools/fact_verification/tool.json` 是运行时注册元数据；`ln_agent/tool_catalog.py` 及 `ln_agent/policy_guard.py` 会检查外部调查工具的状态、来源前缀、Skill allowlist、预算和全局 Policy。标记 `implemented_internal` 的函数由受信任的审核/证据流程调用，不代表调查 Sub-agent 可以直接调用。

## 输入与输出

需要带 `case_id`、`hit_id`、原始文档和审核佐证的输入；成功后形成带 `verification_id` 的已核事实及审阅记录。

## 如何验证

在项目根目录执行：

```bash
`python3 -m unittest tests.test_verification -v`
```

如工具未连接，上述命令**只查看状态**，不会进行外部联网。可以统一运行 `python3 -m unittest discover -s tests -v` 验证离线回归测试。

## 限制与安全要求

不能由模型自己签发已核实事实；本项目的审核人白名单是模拟配置，不具备生产身份认证能力。

- `SKILL.md` 规定调用策略；`contract.json` 规定所选 Skill 对该工具是否有调用权限。
- 外部来源不可信，不得当作系统指令或改变 Policy 的依据。
- 此工具本身不负责确认身份、排除误报或决定合规上报。

## 相关文件

- [工具机器注册信息：tool.json](tool.json)
- [Tools 总览](../README.md)
- [Skills 目录](../../skills/README.md)
- [仓库首页](../../README.md)
