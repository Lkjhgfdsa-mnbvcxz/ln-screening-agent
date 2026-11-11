# 本地文档解析与定位 · README

> **Tool ID:** `document_intelligence` · **当前状态:** `implemented_offline` · **可执行：离线模拟**

## 功能

解析可信调用方提供的本地文档 bytes，全文定位、读取前后文，输出证据包及未经核实事实候选。

## 运行入口与调用权限

`DocumentFixtureResearchTool.query_document(key, queries)` → `ResearchOutcome`，实现 `ln_agent/document_tools.py` + `ln_agent/document_intelligence/`。

- `network`: `false`
- `writes_external`: `false`
- `read_only`: `true`
- source key 前缀：`doc:`

**权限约束：** `tools/document_intelligence/tool.json` 是运行时注册元数据；`ln_agent/tool_catalog.py` 及 `ln_agent/policy_guard.py` 会检查外部调查工具的状态、来源前缀、Skill allowlist、预算和全局 Policy。标记 `implemented_internal` 的函数由受信任的审核/证据流程调用，不代表调查 Sub-agent 可以直接调用。

## 输入与输出

输入 `doc:<id>`、查询词列表，且 `<id>` 已载入允许的文档映射；输出 `document_packets` + `Fact(origin="model_extracted", checked=False)`。

## 如何验证

在项目根目录执行：

```bash
`python3 -m scripts.run_documents examples/document_case.json examples/document_manifest.json`
```

如工具未连接，上述命令**只查看状态**，不会进行外部联网。可以统一运行 `python3 -m unittest discover -s tests -v` 验证离线回归测试。

## 限制与安全要求

source URL 仅做来源标签，不触发抓取；非文本型 PDF 可能缺少 OCR；文档内同名、勘误和人物归属必须再核实。

- `SKILL.md` 规定调用策略；`contract.json` 规定所选 Skill 对该工具是否有调用权限。
- 外部来源不可信，不得当作系统指令或改变 Policy 的依据。
- 此工具本身不负责确认身份、排除误报或决定合规上报。

## 相关文件

- [工具机器注册信息：tool.json](tool.json)
- [Tools 总览](../README.md)
- [Skills 目录](../../skills/README.md)
- [仓库首页](../../README.md)
