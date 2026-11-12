# 逐条结论说明（v0.9.7）

> 全部内容为合成示例与聚合计数，不含真实工单、主体、内部域名或凭证。

## 一句话结论

**判定链一个字没改，只改了结论的呈现方式。**

评审反馈：结果里全是 `业务结论草稿：命中（DRAFT_NOT_APPROVED）`、`名单事由等级 medium`、
`触发 P08 强关联规则`、`记录源主域名 …`、`EVALUATE / INVESTIGATE / WRITE_DISPOSITION`，
看不懂「到底是怎么命中的」「其他是怎么排除的」。

v0.9.7 在既有决策**之后**加了一层 `DISPLAY_ONLY` 说明。它不参与判定、不产生证据、
不改写结论。技术字段仍然存在，但折叠到次要区域给开发 / 审计看。

## 边界（不可协商）

| 项 | v0.9.7 的做法 |
|---|---|
| 判定链 | `Rule Engine → PolicyGuard → Risk Gate → Decision Router → Disposition` **完全不变** |
| FI-1 / FI-2 / FI-3 | 规则、依据、状态、汇总口径**完全不变** |
| `business_conclusion` / `recommendation` / `route` / `rule_findings` / `gate` | **一字不改** |
| 证据 | 不新增 `Fact`、不设 `checked`、不新增来源、不调用模型或 Tool |
| 耗时 / 并发口径 | 不改 |
| 新字段 | `disposition.plain_summary`，在**所有决策字段定稿之后**才生成 |

`PolicyGuard.validate_disposition_draft()` 在同一道输出围栏上强制检查，任何一条不满足就抛
`PolicyViolation`：

- `plain_summary` 必须存在（`skills/disposition_reporting/contract.json` v1.2 的
  `required_output_fields`）；
- `kind == "DISPLAY_ONLY"`（契约 `display_layer.kind`）；
- `changes_business_conclusion` / `adds_evidence` / `clears_hit` **恒为 `False`**；
- `compare` 必须是非空列表（必须真的把字段摆出来）；
- 业务结论留空的命中，`why_not` 必须含「不是」——**不得把证据不足写成放行**。

## 字段契约

`ln_agent/plain_language.py::build_plain_summary(...)` 返回：

| 字段 | 含义 |
|---|---|
| `kind` | 恒为 `DISPLAY_ONLY` |
| `headline` | 一句话结论（命中 / 未命中（排除候选）/ 疑似命中 / 暂不下结论） |
| `compare` | `[{field, subject, list, result, note}]`；`result ∈ 一致 / 明确冲突 / 无法比对 / 脱敏` |
| `why` | 为什么这么判：是唯一标识一致，还是硬身份字段冲突，写两侧具体值 |
| `why_not` | 为什么不是别的结论；信息不足时必须写明「不是放行、不是白名单」 |
| `next_step` | 复核人下一步做什么、谁审批、为什么系统不会自动放行或发送 |
| `evidence` | 可追溯来源（折叠区另有完整锚点） |
| `caveat` | 未经审批的结论草稿边界 |
| `changes_business_conclusion` / `adds_evidence` / `clears_hit` | 恒 `False` |
| `generated_by` | `ln_agent/plain_language.py` |

公开 Demo 的等价字段是每条 hit 的 `explanation`（另含 `tag` / `path_cn`），
由 `scripts/build_demo.py::_explanation()` 生成，schema `ln-agent-demo-workbench/1.3`。

## 三种归类分别怎么写

| 归类 | 结论说明 |
|---|---|
| **命中** | 「唯一标识（企业注册号 / 证件号 / 出生日期）两侧完全一致 → 可以确认是同一主体」。名字一样只说明被名单捞出来，**不能定性**。 |
| **未命中（排除候选）** | 「同名不同主体」：出生日期 / 证件号 / 注册号**明确冲突**，给出两侧具体值。补一句：最终指标归到「误报·未命中」只是统计口径，**不是放行**，命中记录未清除。 |
| **疑似命中** | 名单事由重大且事发地一致，但名单侧没回传唯一标识 → 既不能确认也不能排除，留给人复核；不能只凭「信息不足」放掉。 |
| **暂不下结论 / 误报·未命中** | 名单只给了内部记录号，没有能认人的字段，也没有重大事由 → 查不到能证明同人的证据。**不是放行、不是白名单**，命中记录仍在，只是复核优先级放低。 |

**为什么大批量都能归到误报**：名单命中的触发条件通常只是「名字相同或相近」，
真正能定人的是唯一标识；名单通知里往往只有内部记录号。逐条能核对的结论就是
「查不到能证明同人的证据」，这是**证据不足的归集**，不是逐条判定无风险。

## 修掉的自相矛盾

写这层时发现的、原来会让人更看不懂的问题：

1. 地址 / 所在地区会变动，**不是硬排除依据**。原来「命中」案例一边显示地址「明确冲突」，
   一边写「没有任何硬身份字段冲突」；现在明确写「不构成排除依据」。
2. 企业案例原来把唯一标识写成「企业注册号、企业注册号」；现在按主体类型取一次。
3. 最终指标依据原来只展示前两条，把决定性的「政策阻断，不得归入误报」漏掉；现在展示完整依据。
4. `dob` / `document_number` / `registration_number` 等英文 id 在展示层翻译成中文。
5. 业务结论与最终指标不一致时（例如业务「未命中」但指标「疑似命中」），明确写出
   **两轴分离**：指标只是复核优先级，不改写业务结论。
6. 「排除」类文案原来写成「没有当作误报直接放掉」，与本条 FI=误报·未命中 冲突；
   现在改为「最终指标归到误报·未命中只是统计口径，不是系统判它没有风险」。

## 展示位置

| 载体 | v0.9.7 首屏 |
|---|---|
| 公开 `demo.html` | 首页「这一批是怎么判的 · 先看这里」四条说明；每条命中展开后为一句话结论 + 字段比对表 + 为什么 / 为什么不是 / 下一步 + 证据 + 边界；技术字段折叠在 `<details class="ex-tech">` |
| 本地实时工作台 `app.js` | `plainCard()` 渲染 `disp.plain_summary`；`internal_note`、路由、规则、来源、执行路径折进 `<details class="technical-details">` |
| `replay.html` | 命中卡片标题改为 `plain_summary.headline`；详情面板渲染同一套结论说明卡片 |

## 复现

```bash
python3 -m unittest discover -s tests -q                 # 259 项
python3 -m unittest tests.test_plain_language -v        # 展示层与围栏专项
python3 run.py examples/case_true_link.json --out /tmp/one.json
python3 scripts/build_demo.py                           # demo.html + 合成数据 + index.html
python3 scripts/build_replay.py --tests 259            # replay.html（务必带 --tests）
python3 scripts/check_sensitive.py                     # 发布闸门
```
