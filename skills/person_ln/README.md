# 人员 LN 核验 · README

> **Skill ID:** `SKILL_PERSON_LN_V1` · **版本:** `1.0` · **只读:** `true`
>
> 运行状态：离线主核验 Skill（实际加载契约）。这不是经公司批准的审核制度。

## 1. 解决什么问题

核验入网管理员、法人、董事、UBO 等自然人与 LN 人员命中的身份关联。

**何时调用：** 当 `Hit.entity_type == "person"` 时，作为主 Skill 加载。

## 2. 核验重点

- 双方是否存在**可比、可追溯**的出生日期、证件类型/号码？
- 命中内容所述任职单位、明确事件日期、案号是否属于这一名名单实体？
- 是否有同名不同人的来源冲突或历史信息变化？

## 3. 建议执行方法

1. 首先比较 KYB 与 LN 已有字段；四态记录一致、冲突、缺失、无效。
2. 如需调查，优先围绕机构、职务、案号、明确日期寻找对应来源；保留来源原文。
3. 对于文档中的任职年份，区分事件年份与发布年份；由 Fact Verification 验证人物归属。
4. 提交候选 Fact 和证据锚点，再由 Rule Engine / PolicyGuard 判定。

## 4. 输入、输出与权限

| 项目 | 当前约定 |
| --- | --- |
| 输入 | 当前 `case_id` / `hit_id` 的最小必要事实、待查问题和研究键；来源材料均作为不可信数据处理 |
| 允许的字段 / 结果 | `name`, `dob`, `document_number`, `gender`, `employer`, `role`, `acted_in_year`, `address`, `pep_status`, `photo_comparison`, `event_recency`, `region`, `company_name` |
| 允许工具 | `fixture_research`, `document_intelligence` |
| 预期输出 | 携带 `evidence_id` 的候选 `Fact`、证据定位与调查说明 |
| 判断权限 | **无权**自行批准排除、放行商户、变更政策或写回 LN |

`SKILL.md` 说明*怎样核验*；`contract.json` 是受信任本地**机器契约**；本 README 解释使用方法、边界和维护入口。实际决策由 `ln_agent/evidence.py`、`ln_agent/router.py`、`ln_agent/policy_guard.py` 负责。

## 5. 情景示例（合成场景）

`person` 命中：同名但出生日期冲突 → 记录冲突候选，核对双方信息可靠性，不直接清退/放行；如果命中为制裁类，Risk Gate 的复核要求仍保留。

## 6. 不可越过的边界

- `photo_comparison`、`region`、`role`、`pep_status` 等被配置为禁止单独硬排除的字段。
- 不得按职位倒推年龄；不得用跨省居住、企业存在或照片差异直接排除。
- `SKILL.md` 是调查方法，`contract.json` 决定运行时允许的字段和来源。

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
