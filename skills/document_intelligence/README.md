# 文档智能定位与证据提取 · README

> **Skill ID:** `SKILL_DOCUMENT_INTELLIGENCE_V1` · **版本:** `1.0` · **只读:** `true`
>
> 运行状态：辅助 Skill（按研究键或阶段选择；所依赖的部分工具仍是离线模拟）。这不是经公司批准的审核制度。

## 1. 解决什么问题

把长篇公告、网页、PDF、DOCX、XLSX 中的候选材料快速定位、连同上下文与原文位置交给核实层。

**何时调用：** 研究键以 `doc:` 开头时被选择；由本地文档工具执行实际解析。

## 2. 核验重点

- 待核验姓名/企业/案号在文档的哪些位置出现？
- 相关段落、表格表头、前后文能否确定事件参与者？
- 同文件是否存在勘误、其他同名者、附件或矛盾描述？

## 3. 建议执行方法

1. 解析输入文件为有页码/段落/行位置信息的文本块。
2. 以多关键词定位，读取上下文并进行重要信息补充扫描。
3. 返回 `evidence_packet` 与 `unverified_fact_candidates`，保留 SHA-256、原文、位置及覆盖情况。
4. 所有自动候选默认 `checked=false`，需 FactVerifier 核实来源、人物对应及含义后才可用于硬规则。

## 4. 输入、输出与权限

| 项目 | 当前约定 |
| --- | --- |
| 输入 | 当前 `case_id` / `hit_id` 的最小必要事实、待查问题和研究键；来源材料均作为不可信数据处理 |
| 允许的字段 / 结果 | 依当前阶段决定（见 `contract.json` 的 `output`） |
| 允许工具 | `document_intelligence` |
| 预期输出 | `evidence_packet`, `unverified_fact_candidates` |
| 判断权限 | **无权**自行批准排除、放行商户、变更政策或写回 LN |

`SKILL.md` 说明*怎样核验*；`contract.json` 是受信任本地**机器契约**；本 README 解释使用方法、边界和维护入口。实际决策由 `ln_agent/evidence.py`、`ln_agent/router.py`、`ln_agent/policy_guard.py` 负责。

## 5. 情景示例（合成场景）

一份长监管公告出现多个张某 → 分别定位页面和表格行，提取任职年份候选，同时检查更正文字；不能把另一个张某或发布日期归到当前命中者。

## 6. 不可越过的边界

- 目前是**本地文件**分析，不会自动打开 URL 或联网；扫描版 PDF 可能需要尚未实现的 OCR。
- 对来源缺失、提取覆盖不全、表格结构歧义，应保留“不足以核实”的状态。

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
