# Local Workbench · 本地实时工作台

## 运行

```bash
python3 run.py web             # 只监听 127.0.0.1:8765
python3 run.py web --port 8766 # 自定义端口
```

直接访问 `http://127.0.0.1:8765`。默认不联网、不调用 LLM；仅可选择仓库内的虚构案例。

案例下拉中的 **「WorkBuddy 本地采集 · 合成回放」** 使用 `examples/workbuddy_capture_bundle.json`（纯合成本地暂存包），演示两个授权本地 Tool 通过既有 `SKILL_SELECTED → TOOL_AUTHORIZED → TOOL_STARTED/TOOL_FINISHED → FACTS_RECEIVED → RULE_EVALUATED` 链路接入；该案例由工作台内部调用 `authorized_policy()` 显式开启工具，其他案例仍使用默认离线 Policy。

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

## 静态回放（V0.9.3）

没有 Python 环境的访问者可以直接打开仓库根目录的 `replay.html`，或用 GitHub Pages 在线查看。它把 `examples/workbuddy_capture_replay.json` 中已录制的一次合成案例真实执行事件做成可播放时间线，**不替代**这里的实时 SSE 工作台：

- 工作台：本地起服务、实际并行跑案例、事件边产生边推送。
- 静态回放：事件已录制、单文件离线播放、只含合成数据，供公开演示与评审查看。

两者共用同一套事件字段与业务结论结构。用 `python3 scripts/build_replay.py --tests 242` 重新生成回放；生成器只读取 `examples/` 下的合成输入，绝不读取授权环境里的真实采集包。

## 公开的工单级 Demo（V0.9.4）

`demo.html` 补上了实时工作台**上面缺的那一层**：首页是 8 个工单主体卡片（每张核查单一个主体），点进去是这张单里每条命中的进度、最终业务结论和该条自己的核查说明；不需要 Python 后端、不需要登录，外部评审打开 <https://lkjhgfdsa-mnbvcxz.github.io/ln-screening-agent/demo.html> 即可查看，`?autorun=1` 打开即自动演示 4 workers 并行推进，`#SYN-LN-2602` 可直接深链到 88 条命中的大单。

- 数据：`examples/demo_workbench_data.json`，由 `python3 scripts/build_demo.py` 生成；同一脚本同时生成 `index.html`（Pages 首页入口）。**全部为合成值**，只复现授权本地验证的 8 单 / 154 命中 / 4 workers / 单条实际约 395 ms 的量级（并行后摊到每条约 103 ms）。
- 层级：`工单主体 → 逐条命中 → 单条核查说明与执行路径`。详情页默认渲染 25 条，可继续加载；大批量命中不折叠成一条时间线。
- 主体画像：字段结构来自 WorkBuddy 企查查连接器（`get_company_profile` / `get_company_risk_scan` / `get_executive_risk_scan`），企业 35 项、个人 18 项风险因子。取值全部合成，页面明确标注**未发起实时查询**；连接器本次实时调用因积分不足返回 402，项目内 `tools/qcc/` 仍是 `not_connected`。页面保留连接器口径：**0 命中仅代表结构化维度当前无记录，不等于主体无风险**，须并行核对舆情。
- 耗时口径（v0.9.5 更正）：`Orchestrator.stats.elapsed_ms` 是**整单经 4 workers 并行后的墙钟**，不是各命中耗时之和；单条真实工作量取自 `HIT_FINISHED.duration_ms`（事件顶层字段）。授权实测单条约 394.863 ms，49 / 88 条大单加速比 3.93x / 3.97x，8 张工单是**逐单**运行、累计墙钟 15,922.158 ms；`103.391 ms/命中` 只是 `15922.158 / 154` 的并行摊薄份额。
- 三种墙钟必须分开：**逐单串行** ≈ 15.9 s（实测）、**8 个主体同时开跑且每单各 4 workers** ≈ 9.3 s（总墙钟 = 最慢的单，需 32 并发）、**全局共享 1 个 4-worker 池** ≈ 15.2 s。不能把并行墙钟再除以 4，也不能把摊薄份额当作单条耗时。Demo 动画让 8 张卡片在 t=0 同时开始、按各自墙钟比例完成，命中阶段按 4 条一组推进。
- 与实时工作台的区别：Demo 是已录制形态的静态页，可公开、可离线；真实并行执行与 SSE 事件仍只在 `python3 run.py web` 的本地进程里发生。两者业务结论字段一致，但 Demo 不冒充实时运行。
- 发布闸门：`scripts/build_demo.py::_assert_synthetic()` 与 `tests/test_public_demo.py` 检查真实数据标记、15~18 位证件号、外部资源、8/154 形态、画像口径、耗时算术与首页入口归属。

## 最终指标（V0.9.6）

实时工作台与 JSON 现在同时输出两个**独立轴**，不要混为一谈：

| 轴 | 取值 | 用途 |
|---|---|---|
| `business_conclusion`（业务结论草稿） | 未命中 / 疑似命中 / 命中 / 留空 | 审核判断，全部 `DRAFT_NOT_APPROVED`；证据不足时保持留空 |
| `final_indicator`（最终指标） | 命中 / 疑似命中 / 误报·未命中 | 派生统计口径与复核优先级；**不改变业务结论、不自动放行、不清除命中** |

- 工作台命中列表在业务结论下面多一行「最终指标：…」；详情区在业务结论面板下方单独渲染最终指标、`FI-1/2/3` 规则 id 与逐条依据（`.final-indicator` 面板，视觉上与业务结论区分）。
- `replay.html` 的命中卡片与选中详情也显示最终指标、规则 id 与依据。
- 公开 Demo 首页新增「最终指标 · 全批唯一汇总」面板：三条规则、三标签分布、以及全批唯一的**需人工复核率 11.0%（17 / 154）**；每条命中可按最终指标筛选。
- 规则与边界详见 [`FINAL_INDICATOR.md`](FINAL_INDICATOR.md)。推送前另跑 `python3 scripts/check_sensitive.py` 全仓 + 全历史脱敏闸门。
