# 最终指标（FI-1 / FI-2 / FI-3）与机制边界

> v0.9.6 · 全部内容为合成示例与聚合计数，不含真实工单、主体、内部域名或凭证。

## 1. 一句话结论

**是按项目既有机制做的，同时项目本身确实有缺陷、我也做了修复。** 审核流程没有被重新设计：判定链、证据模型、权限围栏、业务结论三标签、草稿状态、工作台都沿用原项目。修复的是「真实运行把这些既有机制跑不通 / 跑错」的实现缺陷，以及在链路**下游**新增一个不参与判定的派生指标。

---

## 2. 为什么要新增「最终指标」

原项目的 `business_conclusion` 只有 `未命中 / 疑似命中 / 命中`，证据不足时**故意留空**（`NO_CONCLUSION`）。这个保守设计是对的：信息不足不能自动判「未命中」。但在真实批量核查里，154 条命中里有 153 条留空，工作台看起来像「什么都没跑出来」。

评审要的是：每条命中都要有一个**明确的最终归类**，以及一个**可以写进材料的最终指标**。规则按业务口径给定：

| 情形 | 最终指标 |
|---|---|
| 命中 | **命中** |
| 同样缺身份信息，但**名单事由很严重、事发地也一致** | **疑似命中** |
| 没什么特别信息（例如根本拿不到只有通知里才有的身份信息，也不是什么大事） | **误报 / 未命中** |

本实现把「误报 / 未命中」统一写作 **`误报·未命中`**，并明确它只是**复核优先级与统计口径**，不是排除决定。

---

## 3. 三个标签的确定性规则

`ln_agent/final_indicator.py` 只读取既有链路**已经产出**的字段，不调用模型、不查外部接口、不生成新事实。

| 规则 | 标签 | 判定输入（全部来自既有输出） |
|---|---|---|
| **FI-1** | 命中 | `business_conclusion == "命中"` 且 `identity == "strong_link"`；硬匹配规则 `DOCUMENT_EXACT_MATCH` / `COMPANY_REGISTRATION_MATCH` / `DOB_EXACT_MATCH` 写入依据 |
| **FI-2** | 疑似命中 | ① 已有上报草稿 `report_recommended`；或 ② 政策要求合规升级 `mandatory`；或 ③ **重大事由**（`severity ∈ {high, critical}` 且有 `source_ref`）**且事发地一致**；或 ④ 工具 / 政策阻断、来源冲突（这些**不得**归入误报） |
| **FI-3** | 误报·未命中 | 其余：无重大事由或事发地不一致，且命中侧没有可比对的独立身份字段（证件号 / 出生日期 / 注册号缺失或脱敏） |

### 「事发地一致」怎么算（不能靠模型猜）

`_location_consistency()` 只做**结构化字段的精确归一化匹配**：

- 名单侧显式事发地：`risk_event.event_region` / `incident_region` / `event_country` / `jurisdiction`，或 `material_context` 里带 `evidence_id` 的 `region` / `place`；
- 入网主体与命中侧：`region` / `jurisdiction` / `country` / `nationality` / `address` 等事实字段；
- 三类值之间出现精确匹配才算「一致」。**缺值 = 未知，永远不算一致**；脱敏值（`*` / `x` / `X` / `•`）不参与。

这正好对应「同样缺信息，但很严重**同时**事发地也一致 → 疑似命中」：两个条件必须同时成立，缺一个就落到 FI-3。

### 「没什么特别信息」怎么算

`_identity_available()` 检查命中侧 `document_number` / `dob` / `registration_number`。都没有（或全是脱敏值）、又没有可引用的重大事由时，才按 FI-3 归集。这对应「根本无法获取某些只有通知的身份信息，也不是什么大事」。

---

## 4. 边界：它绝对不是新的审核结论

`final_indicator` 是在 `build_disposition()` **算完** `recommendation` / `business_conclusion` / `report` 之后才派生的，输出恒带：

```text
final_indicator_kind                     = "TRIAGE_METRIC"
final_indicator_status                   = "DRAFT_NOT_APPROVED"
final_indicator_does_not_clear_hit       = True
final_indicator_changes_business_conclusion = False
```

`PolicyGuard.validate_disposition_draft()` 会逐项校验，并拒绝：

- 未知标签 / 未声明的规则 id / `APPROVED` 状态 / 空的依据列表；
- `final_indicator == "命中"` 但 `business_conclusion != "命中"`（不允许升级未确认命中）；
- `final_indicator == "误报·未命中"` 但业务结论是 `命中` / `疑似命中`、或 `report_recommended=True`、或 `identity=strong_link`（不允许降级）；
- `does_not_clear_hit` 被改成 `False`、`changes_business_conclusion` 被改成 `True`。

Skill 契约 `skills/disposition_reporting/contract.json` 里同时保留原有的
`prohibited_shortcuts: ["信息不足自动判误报", ...]`。它约束的是 **disposition**；
派生指标单独声明在 `derived_metric` 段，列明 `must_not_change` 与 `prohibited_actions`：
**不清除 / 白名单命中、不自动放行、不自动发送、不因信息不足创建人工调查任务、不由大模型生成判定依据**。

> 换句话说：`误报·未命中` 是「这批可以先放低复核优先级」的统计标签，
> 不是「这条已经排除、可以放行」。LN 工单状态、上报草稿、业务结论草稿全部不变。

---

## 5. 工单级与全批级汇总

- `derive_case_indicator(labels)`：取本单出现过的**最高等级**标签，输出三标签分布、`escalation_hits`、`escalation_rate`。
- 全批唯一汇总指标：**需人工复核率 =（命中 + 疑似命中）/ 全部命中记录**。
- 合成 Demo 复刻真实量级：8 个工单主体、154 条命中 → 命中 1 / 疑似命中 16 / 误报·未命中 137 → **需人工复核率 11.0%（17 / 154）**。其中 5 条是「业务结论仍留空、但重大事由 + 事发地一致」被 FI-2 提升的样例，用来演示评审给的那条规则。

实时工作台（`ln_agent/workbench/static/app.js`）在业务结论面板下面单独渲染最终指标与依据；公开 Demo 在首页给出全批汇总面板，每条命中同时显示「业务结论」与「最终指标」两个轴。

---

## 6. 机制边界与优化清单

### 6.1 完全沿用、没有重做

| 项目机制 | 位置 |
|---|---|
| `Rule Engine → PolicyGuard → RiskGate → Decision Router → Disposition` 顺序与判定逻辑 | `ln_agent/router.py`, `ln_agent/rules/`, `ln_agent/policy_guard.py`, `ln_agent/risk_gate.py` |
| `Fact` 四态、`eligible_for_hard()` 来源白名单、脱敏值不参与硬相等 / 冲突 | `ln_agent/models.py`, `ln_agent/evidence.py` |
| Skill `contract.json` + Tool `tool.json` 权限登记；`check_tool_call()` / `validate_facts()` / `validate_disposition_draft()` | `skills/`, `tools/`, `ln_agent/policy_guard.py` |
| 模型事实恒为 `model_extracted / checked=false`，不得触发硬规则 | `ln_agent/workbuddy_adapters.py`, `ln_agent/policy_guard.py` |
| 业务结论三标签 + 草稿状态；不自动发送 / 放行 / 关闭工单 | `ln_agent/disposition.py` |
| 本地 SSE 实时工作台、Reviewer ledger、既有测试的行为契约 | `ln_agent/workbench/`, `ln_agent/review_store.py`, `tests/` |

### 6.2 项目自身缺陷（真实运行暴露，已修 + 回归测试）

| # | 缺陷 | 影响 | 修复 / 回归 |
|---|---|---|---|
| 1 | 授权本地 `build_authorized_cases.py` 只把姓名交给引擎，丢弃 `分数 / 记录源 / ID号码 / LN报警ID / 地址 / 申请人 USCC` | 154 条几乎全「无结论」，真实命中单被判成留空 | 重建既有 `Hit.risk_event` 通道；补结构化事实；真实命中单恢复「疑似命中」 |
| 2 | `disposition.py` 证据不足分支吞掉逐条上下文 | 150+ 条说明塌成模板 | 每条写入记录源、主域名、LN 记录号、缺字段；`tests/test_per_hit_reason.py`（154/154 不同） |
| 3 | `run_authorized.py` 从 `details` 取 `HIT_FINISHED.duration_ms`，实际在事件顶层 | 154 个 null，性能统计失效 | 改取顶层字段；从事件日志重算三种墙钟 |
| 4 | 把整单并行后的 `Orchestrator.stats.elapsed_ms` 当单条耗时再除以 4 | 4 倍加速算两次；串行累计墙钟被标成「并行总墙钟」 | 区分单条工作量 / 单内墙钟 / 逐单累计 / 全批同时开跑；Demo 动画改为 m 主体同时开始 |
| 5 | `ReviewStore.backup()` 用 `with sqlite3.connect()`（只管事务不关连接） | 句柄泄漏 + `ResourceWarning` | `closing()`；`tests/test_v05.py` 断言两连接都关闭 |
| 6 | `build_replay.py` 覆盖 `index.html` | Demo 入口被单案例回放抢走 | 入口归 `build_demo.py`；`tests/test_public_demo.py` 锁定 |
| 7 | 中文 provider 类别别名缺失 | `SCREENING_REVIEW_REQUIRED` 被静默丢弃 | `ln_agent/risk_categories.py` 补别名 |
| 8 | 初始提交测试文件含真实工单号与真实企业名 | 公开仓库**历史**残留真实标识 | 重写 git 历史清除；`scripts/check_sensitive.py` + `tests/test_publication_gate.py` 全仓 / 全历史闸门 |

### 6.3 在既有链路上新增（不是另起炉灶）

- `workbuddy_browser_readonly` / `workbuddy_llm_capture` 两个 Tool + `workbuddy_capture` Skill，通过 `tool_for_source_key()` 查表挂到 Router，默认 Policy **不授权**，需 `authorized_policy()`。
- `Decision.research_facts`：调研事实的完整来源锚点（工具、action key、origin、checked、evidence_id、source_url）。
- 公开合成执行回放 `replay.html`、按工单主体的静态 Demo `demo.html`、企查查字段结构的合成主体画像。
- **最终指标**（本文件）——纯下游派生指标。
- 发布闸门 `scripts/check_sensitive.py`：按形态扫描全部跟踪文件与全部历史提交，不存储任何真实值；可用仓库外词表加跑。

### 6.4 明确没有做

- 没有改任何审核判定规则、没有新增硬排除规则、没有让模型自行定罪或编造依据；
- 没有公网 Python 后端、没有生产身份认证、没有向 LN / BOSS 写回；
- 没有把企查查连接器说成「已实时查询」（本次实时调用返回 `402 credit_balance_insufficient`，项目内 `tools/qcc/` 仍为 `not_connected`，画像取值全部合成）；
- 没有把真实业务数据放进公开仓库。

---

## 7. 复现命令

```bash
python3 -m unittest tests.test_final_indicator -v     # 14 项：三条规则 + 围栏 + 汇总
python3 -m unittest tests.test_publication_gate -v    # 8 项：全仓 + 全历史脱敏闸门
python3 scripts/build_demo.py                          # 重生成 demo.html / 数据 / index.html
python3 scripts/build_replay.py --tests 242            # 重生成 replay.html
python3 scripts/check_sensitive.py                     # 推送前发布闸门（退出码 0 = 干净）
python3 -m unittest discover -s tests -q               # 242 项全量回归
```
