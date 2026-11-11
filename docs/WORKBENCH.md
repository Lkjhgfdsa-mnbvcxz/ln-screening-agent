# Local Workbench · 本地实时工作台

## 运行

```bash
python3 run.py web             # 只监听 127.0.0.1:8765
python3 run.py web --port 8766 # 自定义端口
```

直接访问 `http://127.0.0.1:8765`。默认不联网、不调用 LLM；仅可选择仓库内的虚构案例。

## 真实数据通路（不是 AI 自述进度）

1. `POST /api/runs`：选定合成 fixture，创建 `RunRecord`；后台运行 `Orchestrator.run(max_workers=N)`。
2. `Orchestrator` 使用 `ThreadPoolExecutor` 并行分配命中，完成一条立即发送 `HIT_RESULT_READY`。
3. `DecisionRouter.run_hit` 的实际代码调用点同步产生 `SKILL_SELECTED`、`RULE_EVALUATED`、`POLICY_CHECK`、`TOOL_STARTED`、`TOOL_FINISHED`、`HIT_FINISHED` 等事件。
4. `GET /api/runs/{id}/events?after=0`：通过 SSE 将新事件传给浏览器，无重复 LLM 调用。
5. `GET /api/runs/{id}`：获取当前快照、已完成结果与按阶段汇总的真实耗时。
6. `GET /api/runs/{id}/report`：完成后导出全部合成案例 JSON 报告。

每个事件包含 `seq`、`elapsed_ms`、`stage`、`kind`、`case_id`、`hit_id`、`details`，已计时事件还有 `duration_ms`。阶段耗时可以重叠，**不能简单求和代替整单耗时**。

## 原有审核结论

- `examples/prior_reviews_synthetic.json` 是**虚构既有审核记录**；包含 `case_id`、`hit_id`、结论、是否上报、时间和来源引用。
- 工作台对其作只读比较：方向一致或潜在冲突，历史信息**不注入 Rule Engine 的核验事实**。
- 本地导入不是授权签署。即使 JSON 声称是已核实，仍标记 `IMPORTED_UNVERIFIED`。
- 真实 BOSS 历史审核接入必须单独实现经授权只读适配器，保留历史与版本关系，不允许新结果自动覆盖旧决定。

## 大模型接口

- 默认无 Key；`python3 run.py llm-status` 只检查配置，不请求网络。
- 复制 `.env.example` 至 `.env`，填写 `LN_LLM_BASE_URL`、`LN_LLM_MODEL`、`LN_LLM_API_KEY`（本地不要求 Key），启用 `LN_LLM_ENABLED=true`。远程 HTTPS 另外需 `LN_LLM_ALLOW_EXTERNAL=true`。
- 代码接口：`LLMExtractionAdapter.extract_candidates(excerpt, evidence_id, allow_external_text=True)`。
- 只有显式调用该方法才会发送文本；现有离线演示仍走 `FixtureResearchTool`。
- 模型仅能提取未核实候选事实；生产数据出站需要公司的数据安全与授权评审。

## 实现范围与下一步

已实现：单进程多命中并发、逐条事件推送、HTML 本地展示、耗时埋点、历史审核对照、合成案例回归、可选模型提取接口。

未实现：真实 LN/BOSS/QCC 联网、模型驱动的自动搜索计划、生产级账号权限与长期任务恢复、任意用户文档上传、真正的制裁名单在线核验。可由 WorkBuddy 在这些现有接口上继续扩展，**不要把“在网页显示 Skill 名称”误认为自动满足所有审核规则**。

## 业务结论显示（V0.9.2）

首页及单条命中顶部仅显示 `disposition.business_conclusion`：**未命中、疑似命中、命中**。当前尚无充分依据形成业务结论时显示 `—`，另提示未形成结论；这不是第四类业务结论。内部路由、引擎评分、规则来源仍在「查看证据来源与执行细节」折叠区和实时事件面板。历史结论独立呈现，不能覆盖新判断。JSON 原样保留全部技术字段及新增业务结论字段。
