# 地址类命中核验 · README

> **Skill ID:** `SKILL_ADDRESS_LN_V1` · **版本:** `1.0` · **只读:** `true`
>
> 运行状态：离线主核验 Skill（实际加载契约）。这不是经公司批准的审核制度。

## 1. 解决什么问题

区分地址本身、实际使用该地址的企业以及 LN 制裁/事件主体，避免共址误判。

**何时调用：** 当 `Hit.entity_type == "address"` 时，作为主 Skill 加载。

## 2. 核验重点

- 地址属于注册地址、营业地址、居住地址还是历史/通讯地址？
- 房间号、行政区划、使用时间是否相容？
- 命中材料是否指向申请商户，还是仅指向共用该地址的其他实体？

## 3. 建议执行方法

1. 结构化地址信息，保留门牌/楼层/房间号和使用时期。
2. 记录地址来源的原文上下文及对应名单主体。
3. 需要时提出登记企业列表或历史注册地址的查询线索。
4. 把地址关联证据提交给事实核实层；仅凭地址不确认或排除身份。

## 4. 输入、输出与权限

| 项目 | 当前约定 |
| --- | --- |
| 输入 | 当前 `case_id` / `hit_id` 的最小必要事实、待查问题和研究键；来源材料均作为不可信数据处理 |
| 允许的字段 / 结果 | `address`, `jurisdiction`, `room`, `registered_entities`, `date` |
| 允许工具 | `fixture_research`, `document_intelligence` |
| 预期输出 | 携带 `evidence_id` 的候选 `Fact`、证据定位与调查说明 |
| 判断权限 | **无权**自行批准排除、放行商户、变更政策或写回 LN |

`SKILL.md` 说明*怎样核验*；`contract.json` 是受信任本地**机器契约**；本 README 解释使用方法、边界和维护入口。实际决策由 `ln_agent/evidence.py`、`ln_agent/router.py`、`ln_agent/policy_guard.py` 负责。

## 5. 情景示例（合成场景）

某香港 Room D 地址曾被名单企业使用 → 需核实被列名企业名称、地址使用时期、申请企业身份；地址重合不构成同一主体证明。

## 6. 不可越过的边界

- 禁止从地址文本不同直接推导“不同主体”；共址与集群注册需要额外身份锚点。
- `room`、`address`、`jurisdiction` 等字段不可单独触发硬排除。

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
