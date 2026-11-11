# 地址命中核验

**ID:** `SKILL_ADDRESS_LN_V1` · **状态：** 运行时生效的核验 Skill（离线模拟输入）

## 目标

区分注册地址/经营地址/住宅与使用时期，识别共址企业。仅从来源中提取可核实的事实，提出下一步调查动作。最终排除、关联与上报由 Rule Engine + PolicyGuard 裁定。

## 关注字段

address, jurisdiction, room, registered_entities, date

## 建议查询顺序

ln → registry → official → doc → web → boss → model。真实外部接口未连接，当前使用模拟研究数据/本地文档；`boss:`/`model:` 仅授权本地环境显式开启，详见 `skills/workbuddy_capture/`。

## 不得依据以下字段单独排除

address, region, room, jurisdiction

## 禁止捷径

- 共享办公地址即制裁命中
- 地址字符串不同即不存在关联

## 证据输出

每项事实关联证据 ID、原始出处及位置。未经人工核实的抽取结果必须保持 `checked=false`。
