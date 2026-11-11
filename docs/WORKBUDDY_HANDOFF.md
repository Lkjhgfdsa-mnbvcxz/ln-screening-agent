# WorkBuddy 接续开发 · v0.9

## 先运行（不需要模型 Key）

```bash
python3 run.py web
# http://127.0.0.1:8765
python3 run.py demo
python3 run.py llm-status
python3 -m unittest discover -s tests -q
```

本地可运行基线包含：规则与风险闸门、动态路由、并行命中、结构化证据、文档智能、来源核实、来源佐证、REOPEN、简洁处置草稿，以及 **真实代码事件驱动**的 HTML/SSE 工作台。前端页面只展示实际 `on_event` 埋点和后端结构化结果，不需要让 AI 逐条“汇报进度”。

## 先从这三个入口接续

| 入口 | 作用 |
|---|---|
| `ln_agent/workbench/server.py` | 本地 HTTP + SSE 服务，保留只读 localhost 安全边界 |
| `ln_agent/workbench/runner.py` | 多命中任务、事件历史、耗时快照、既有审核记录导入与对照 |
| `ln_agent/llm_adapter.py` | 可配置 OpenAI-compatible 模型事实抽取接口，**默认未启用** |

更多具体接口：[`WORKBENCH.md`](WORKBENCH.md) 与根目录 [`AGENTS.md`](../AGENTS.md)。

## 必须保持的业务边界

1. 原有审核结论是**已有工作流记录**，不是 Agent 自动认定的身份事实。展示并对照，不静默覆盖；真实来源需获授权只读 BOSS 适配器。
2. 正式筛查风险处置由政策控制。`unresolved` 可以同时生成疑似命中建议；**信息不足不自动创建人工调查队列**。不自动提交、放行、白名单或通知。
3. Skill 文档与 `contract.json` 必须共同维护；真正的权限限制在 `PolicyGuard` 和工具注册表的运行时代码里执行。不同命中不得共享身份结论。
4. 模型只负责结构化事实候选和必要的文本理解，提取结果 `checked=false`，不允许自证已核实；不得将内部商户资料发到未经批准的模型端点。
5. 真实 LN/BOSS、Web、QCC/注册处连通、任务断点恢复、生产身份认证与实时外部调用性能测试仍未实现；**不要在 README 上宣称已实现**。

## 继续开发的优先次序

- 先把经授权的只读数据适配器接入 `InvestigationAgent`，保证真实来源、工具查询、证据定位和耗时事件完整；需要关注项目中的显式 Skill/Tool 合约。
- 有真实可用的工具后，再在 PolicyGuard 约束下接入可选 LLM 的调查规划；不要把路由判断权交给模型，也不要用模型“监工”增加延迟。
- 再补多工单持久运行/中断恢复、URL 安全、并发限额与用户权限，最后评估真实场景性能和业务规则准确率。

所有提交请附代码、测试、模块 README，使用**纯合成 fixture**；GitHub 仓库不得包含真实商户资料、Cookie 或 API Key。
