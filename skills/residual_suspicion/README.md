# 残余可疑度辅助分析 · README

> **Skill ID:** `SKILL_RESIDUAL_SUSPICION_V1` · **版本:** `1.0` · **只读:** `true`
>
> 运行状态：辅助 Skill（按研究键或阶段选择；所依赖的部分工具仍是离线模拟）。这不是经公司批准的审核制度。

## 1. 解决什么问题

身份仍未确定、调查合理穷尽时，为人工复核提供证据充分性判断及谨慎的上报建议。

**何时调用：** 仅当 Router 进入 `suspicion` 阶段时被选择；并非每条命中都需要。

## 2. 核验重点

- 是否存在独立的区分性字段，足以输出数值评分？
- 姓名、地域、任职、PEP 时效等软证据与风险类别有什么关系？
- 是否存在 Risk Gate 强制复核要求，禁止低分绕过？

## 3. 建议执行方法

1. 优先判断 `evidence_sufficiency`，不足时返回 `score=null`。
2. 对充分场景输出因子贡献、负向因素、解释性建议。
3. 将评分仅作为人工调查优先级建议，不写回 LN、不决定商户准入。

## 4. 输入、输出与权限

| 项目 | 当前约定 |
| --- | --- |
| 输入 | 当前 `case_id` / `hit_id` 的最小必要事实、待查问题和研究键；来源材料均作为不可信数据处理 |
| 允许的字段 / 结果 | 依当前阶段决定（见 `contract.json` 的 `output`） |
| 允许工具 | 无独立外部工具调用权限 |
| 预期输出 | `sufficiency`, `advisory_recommendation` |
| 判断权限 | **无权**自行批准排除、放行商户、变更政策或写回 LN |

`SKILL.md` 说明*怎样核验*；`contract.json` 是受信任本地**机器契约**；本 README 解释使用方法、边界和维护入口。实际决策由 `ln_agent/evidence.py`、`ln_agent/router.py`、`ln_agent/policy_guard.py` 负责。

## 5. 情景示例（合成场景）

只有姓名相同的制裁命中 → 仍是 `INSUFFICIENT_EVIDENCE_MANUAL_ASSESSMENT` 方向，制裁警报的人工复核要求保留；不会给出虚假的精确分数。

## 6. 不可越过的边界

- 演示权重/阈值未经历史案例校准或公司批准。
- `score` 不是身份确认概率，也不是自动上报或豁免依据。

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
