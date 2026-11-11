# Agent Roles（当前实现）

- **Orchestrator（主调度器）：** `ln_agent/orchestrator.py`。按命中并发、聚合审阅结果。当前是确定性 Python 编排。
- **Decision Router（决策路由器）：** `ln_agent/router.py`。按每条命中状态决定查证/结束/RSA，并重新评估。
- **Investigation Agent（受限调查子代理）：** `ln_agent/tools.py::InvestigationAgent`，调用 local fixture/doc adapters。**当前不使用 LLM 自主规划或真实外网搜索。**
- **Suspicion Agent：** `ln_agent/suspicion.py`，仅在穷尽身份调查后运行候选解释性评估。
- **Disposition Writer（内部输出模块）：** `ln_agent/disposition.py`，在 Router 收口时输出简洁内部填写内容与可选的合规复核草稿；受 `PolicyGuard` 校验，**不是**新 LLM Sub-agent，不能发送。
- **Rule Engine / PolicyGuard / Risk Gate：** `ln_agent/evidence.py` + `ln_agent/rules/registry.py` / `policy_guard.py` / `risk_gate.py`。它们是可测试的确定性组件，**不是 Agent**。

总系统可以叫 Agent System / Agent Harness Prototype，但不能把现有 mock 调查称作已具备联网自主行动能力的 LLM Agent。

## 说明：哪些是「真 Agent」？

本项目的 `InvestigationAgent` 目前是可测试的受限执行器，会在路由器授权后调用模拟研究工具；没有真实的 LLM 推理、规划/重规划机制。`SuspicionAgent` 是确定性评分与说明逻辑。你可以以它们作为接入自主模型的边界，但应先完成模型输出结构校验、调用成本/敏感资料控制和来源验证。

## Real-time local execution (v0.9)

The `Orchestrator` dispatches independent hit tasks. `DecisionRouter` emits structured rule, Policy, Skill, tool and disposition events, which are collected by [`ln_agent/workbench/runner.py`](../ln_agent/workbench/runner.py). The dashboard reads those events directly, without extra LLM turns. Optional model integration is described in [`docs/WORKBENCH.md`](../docs/WORKBENCH.md).
