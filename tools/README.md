# Tools · 工具注册表与真实连接状态

此目录包括 **9 个工具描述**。每个工具有 `README.md`（使用/限制/接口说明）与 `tool.json`（程序读取的机器注册信息）。工具数量不等于已连接的 API 数量。

| Tool | 状态 | 作用与实际入口 |
| --- | --- | --- |
| [fixture_research](fixture_research/README.md) | `implemented_offline` | `ln_agent.tools.FixtureResearchTool.query`，合成研究数据 |
| [document_intelligence](document_intelligence/README.md) | `implemented_offline` | `ln_agent.document_tools.DocumentFixtureResearchTool.query_document`，本地文档 |
| [fact_verification](fact_verification/README.md) | `implemented_internal` | `ln_agent.fact_verification.FactVerifier.verify_packet`，受信任内部核实 |
| [source_corroboration](source_corroboration/README.md) | `implemented_internal` | `ln_agent.corroboration.assess_corroboration`，独立佐证 |
| [ln_readonly](ln_readonly/README.md) | `not_connected` | LN 只读采集：待授权开发 |
| [official_web](official_web/README.md) | `not_connected` | 真实官网检索：待安全审查/开发 |
| [qcc](qcc/README.md) | `not_connected` | 企查查 API：待授权开发 |
| [company_registry](company_registry/README.md) | `not_connected` | 官方登记处：待按司法辖区开发 |
| [disposition_writer](disposition_writer/README.md) | `implemented_internal` | `ln_agent.disposition.build_disposition`，短说明及合规报告草稿，不发送 |

**注意：** `fixture_research` 中的 `ln:`、`official:`、`qcc:` 等只是合成数据 key 前缀，不证明连接真实服务。内部核实工具也不会直接作为任意 Sub-agent 可调用 API 暴露。

代码由 `ln_agent/tool_catalog.py` 加载机器注册信息，并通过 `ln_agent/policy_guard.py` 限制支持的调用行为。`not_connected` 状态默认不可调用。

```bash
python3 run.py inspect
python3 run.py demo
python3 -m unittest discover -s tests -v
```

[返回项目首页](../README.md) · [查看核验 Skills](../skills/README.md)

- [`llm_extraction/`](llm_extraction/): optional OpenAI-compatible fact-extraction adapter; **disabled and never called by default**.
