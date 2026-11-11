# Skills · 核验能力与运行时契约

此目录包括 **7 个专项 Skill**。每个 Skill 都有三个文件：

- **`README.md`**：面向开发、审核及交接人员——功能、输入输出、调用方式、示例、限制和运行状态。
- **`SKILL.md`**：调查策略和领域方法，供 Agent/开发人员阅读；不是获批准的审核制度。
- **`contract.json`**：受信任的本地机器契约，包含允许字段、来源、工具范围及禁止快捷判断；由 `ln_agent/skill_catalog.py` 加载。

| Skill | 主要用途 | 触发/适用 | 说明 |
| --- | --- | --- | --- |
| [person_ln](person_ln/README.md) | 人员姓名/证件/生日/履历核验 | `entity_type=person` | 离线主 Skill，契约实际生效 |
| [company_ln](company_ln/README.md) | 企业注册号/历史名称/关联人员 | `entity_type=company` | 离线主 Skill，契约实际生效 |
| [address_ln](address_ln/README.md) | 地址类型/时期/共址消歧 | `entity_type=address` | 离线主 Skill，契约实际生效 |
| [document_intelligence](document_intelligence/README.md) | 长文档快速定位、上下文、原文锚点 | `doc:` | 本地文档解析可运行；自动提取未核实 |
| [source_recovery](source_recovery/README.md) | 失效来源、替代来源线索 | `ln:`/`official:`/`web:` | 只能读取离线 fixture；未联网 |
| [residual_suspicion](residual_suspicion/README.md) | 身份未定时证据充分性/可疑度建议 | `phase=suspicion` | 演示权重，仅建议，无放行权 |
| [disposition_reporting](disposition_reporting/README.md) | 生成简洁内部说明与疑似命中上报草稿 | 每条命中收口 | 确定性代码运行，来源关联，不自动发送 |

**运行时边界：** 主 Agent 通过 `select_skills(entity_type, research_keys, phase)` 选择契约；`PolicyGuard` 对当前可执行工具进行实际拦截，但某些自然语言禁令仍是领域指导，**不能将其视为每条均已经编译为硬校验**。后续修改 `contract.json` 必须增加对应测试。

```bash
python3 run.py inspect
python3 -m unittest discover -s tests -v
```

[返回项目首页](../README.md) · [查看工具目录](../tools/README.md)
