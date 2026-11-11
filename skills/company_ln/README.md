# 企业 LN 核验 · README

> **Skill ID:** `SKILL_COMPANY_LN_V1` · **版本:** `1.0` · **只读:** `true`
>
> 运行状态：离线主核验 Skill（实际加载契约）。这不是经公司批准的审核制度。

## 1. 解决什么问题

定位被列名企业，区分商户与同名企业、历史名称、注册编号及实际关联主体。

**何时调用：** 当 `Hit.entity_type == "company"` 时，作为主 Skill 加载。

## 2. 核验重点

- 登记司法辖区与注册号是否相同，资料是否处于同一时间点？
- 公司是否曾更名、迁址、重组，或者多个企业共用地址？
- 名单里的公司与申请公司/法人/股东是否有可信的实体关联？

## 3. 建议执行方法

1. 先比较主体名称、注册号、司法辖区和股东/董事字段。
2. 注册号缺失时形成有针对性的查询问题；仅查合规批准的数据源。
3. 取得原始登记或处罚来源后抽取有证据位置的候选事实。
4. 不同企业共址只作为调查线索，不共享实体结论。

## 4. 输入、输出与权限

| 项目 | 当前约定 |
| --- | --- |
| 输入 | 当前 `case_id` / `hit_id` 的最小必要事实、待查问题和研究键；来源材料均作为不可信数据处理 |
| 允许的字段 / 结果 | `company_name`, `registration_number`, `jurisdiction`, `address`, `director`, `owner` |
| 允许工具 | `fixture_research`, `document_intelligence` |
| 预期输出 | 携带 `evidence_id` 的候选 `Fact`、证据定位与调查说明 |
| 判断权限 | **无权**自行批准排除、放行商户、变更政策或写回 LN |

`SKILL.md` 说明*怎样核验*；`contract.json` 是受信任本地**机器契约**；本 README 解释使用方法、边界和维护入口。实际决策由 `ln_agent/evidence.py`、`ln_agent/router.py`、`ln_agent/policy_guard.py` 负责。

## 5. 情景示例（合成场景）

LN 企业名相似而登记编号不同 → 先核验登记编号种类、历史变更及主体对应关系；不因“不同”或“同址”自动排除。

## 6. 不可越过的边界

- `address`、`company_name`、`business_address` 禁止独立作为硬排除字段。
- 当前没有可调用的真实企查查或境外官方登记接口；`qcc/` 与 `company_registry/` 仅是禁用工具定义。

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
