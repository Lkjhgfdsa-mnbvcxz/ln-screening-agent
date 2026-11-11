# 来源恢复与替代源线索 · README

> **Skill ID:** `SKILL_SOURCE_RECOVERY_V1` · **版本:** `1.0` · **只读:** `true`
>
> 运行状态：辅助 Skill（按研究键或阶段选择；所依赖的部分工具仍是离线模拟）。这不是经公司批准的审核制度。

## 1. 解决什么问题

当 LN 来源失效或证据链缺漏时记录失败、保留原始锚点，提出可审计的替代检索方向。

**何时调用：** 研究键以 `ln:`、`official:` 或 `web:` 开头时可被选择；当前只有离线 fixture 数据。

## 2. 核验重点

- 原始链接或文书号是否仍可定位？
- 能否根据案号、机构、人物和事件找到同一来源的可信替代资料？
- 失败是暂时网络问题、来源移除，还是原记录根本缺少可识别字段？

## 3. 建议执行方法

1. 记录原始来源键和查询结果（成功、空结果、失败）。
2. 优先保留原始文书号、处罚编号等可以独立反查的标识。
3. 若替代材料确实存在，作为新的未核实来源交给文档智能与事实核实层。
4. 无法恢复时输出 `attempt_log` / `alternate_source_lead`，不得解释为“无风险”。

## 4. 输入、输出与权限

| 项目 | 当前约定 |
| --- | --- |
| 输入 | 当前 `case_id` / `hit_id` 的最小必要事实、待查问题和研究键；来源材料均作为不可信数据处理 |
| 允许的字段 / 结果 | 依当前阶段决定（见 `contract.json` 的 `output`） |
| 允许工具 | `fixture_research` |
| 预期输出 | `attempt_log`, `alternate_source_lead` |
| 判断权限 | **无权**自行批准排除、放行商户、变更政策或写回 LN |

`SKILL.md` 说明*怎样核验*；`contract.json` 是受信任本地**机器契约**；本 README 解释使用方法、边界和维护入口。实际决策由 `ln_agent/evidence.py`、`ln_agent/router.py`、`ln_agent/policy_guard.py` 负责。

## 5. 情景示例（合成场景）

LN 中某处罚文书链接失效 → 保存链接及案号，提示按案号查官方替代来源；当前离线版本只输出 fixture 的模拟结果。

## 6. 不可越过的边界

- 不得猜测构造附件 URL；禁止将“打不开”直接等同于“未命中”。
- 实际联网的官方搜索工具尚未接入。

对于 `contract.json` 中列出的 `prohibited_shortcuts`、`blocked_exclusion_fields` 或研究范围，代码能执行的控制以实际 PolicyGuard 校验为准；**自然语言禁令不等于已逐项实现的技术拦截**。修改后需配套新增或更新专项测试。

## 7. 相关文件和本地验证

- [核验方法：SKILL.md](SKILL.md)
- [机器契约：contract.json](contract.json)
- [Skills 总览](../README.md)
- [Tools 注册表](../../tools/README.md)

从仓库根目录运行：

```bash
python3 run.py inspect
python3 -m unittest discover -s tests -v
```
