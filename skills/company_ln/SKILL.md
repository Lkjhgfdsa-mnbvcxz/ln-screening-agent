# 企业命中核验

**ID:** `SKILL_COMPANY_LN_V1` · **状态：** 运行时生效的核验 Skill（离线模拟输入）

## 目标

企业注册号、登记地、历史名称及股东董事关联核验。仅从来源中提取可核实的事实，提出下一步调查动作。最终排除、关联与上报由 Rule Engine + PolicyGuard 裁定。

## 关注字段

company_name, registration_number, jurisdiction, address, director, owner

## 建议查询顺序

ln → registry → official → doc → qcc → web。真实外部接口未连接，当前使用模拟研究数据/本地文档。

## 不得依据以下字段单独排除

address, company_name, business_address

## 禁止捷径

- 地址相同即认定同一企业
- 营业地址不同即自动排除

## 证据输出

每项事实关联证据 ID、原始出处及位置。未经人工核实的抽取结果必须保持 `checked=false`。
