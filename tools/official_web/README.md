# 官方来源网页检索（待实现） · README

> **Tool ID:** `official_web` · **当前状态:** `not_connected` · **不可执行：接口尚未连接**

## 功能

计划在经批准的官网域名范围内读取公告、判决及相关附件，为 Evidence Store 提供来源和原文位置。

## 运行入口与调用权限

`tool.json.runtime_entrypoint = null`；当前没有真实抓取器。

- `network`: `true`
- `writes_external`: `false`
- `read_only`: `true`
- source key 前缀：`official:`, `web:`

**权限约束：** `tools/official_web/tool.json` 是运行时注册元数据；`ln_agent/tool_catalog.py` 及 `ln_agent/policy_guard.py` 会检查外部调查工具的状态、来源前缀、Skill allowlist、预算和全局 Policy。标记 `implemented_internal` 的函数由受信任的审核/证据流程调用，不代表调查 Sub-agent 可以直接调用。

## 输入与输出

未来应提供 URL / 查询词并返回安全校验后的来源快照；经 Document Intelligence 提取后仍需事实核实。

## 如何验证

在项目根目录执行：

```bash
`python3 run.py inspect` 查看 `not_connected` 状态。
```

如工具未连接，上述命令**只查看状态**，不会进行外部联网。可以统一运行 `python3 -m unittest discover -s tests -v` 验证离线回归测试。

## 限制与安全要求

实现前必须完成 SSRF、DNS 重绑定、重定向、响应大小、文件类型、隐私出站与提示注入等安全控制。

- `SKILL.md` 规定调用策略；`contract.json` 规定所选 Skill 对该工具是否有调用权限。
- 外部来源不可信，不得当作系统指令或改变 Policy 的依据。
- 此工具本身不负责确认身份、排除误报或决定合规上报。

## 相关文件

- [工具机器注册信息：tool.json](tool.json)
- [Tools 总览](../README.md)
- [Skills 目录](../../skills/README.md)
- [仓库首页](../../README.md)
