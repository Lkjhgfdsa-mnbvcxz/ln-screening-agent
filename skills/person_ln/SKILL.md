# 人员命中核验

**ID:** `SKILL_PERSON_LN_V1` · **状态：** 运行时生效的核验 Skill（离线模拟输入）

## 目标

人员姓名、出生日期、完整证件、履历、任职时间与身份冲突核验。仅从来源中提取可核实的事实，提出下一步调查动作。最终排除、关联与上报由 Rule Engine + PolicyGuard 裁定。

## 关注字段

name, dob, document_number, gender, employer, role, acted_in_year, address, pep_status, photo_comparison, event_recency, region, company_name

## 建议查询顺序

ln → official → doc → web → qcc → boss → model。真实外部接口未连接，当前使用模拟研究数据/本地文档；`boss:`（已登录浏览器只读采集）与 `model:`（会话内模型结构化抽取）仅在授权本地环境显式开启，详见 `skills/workbuddy_capture/`。

## 不得依据以下字段单独排除

region, address, business_region, photo_comparison, pep_status, role, employer

## 禁止捷径

- 职位推定出生年份
- 跨省居住即排除
- 服刑且存在公司即排除
- 仅凭人脸照片自动排除

## 证据输出

每项事实关联证据 ID、原始出处及位置。未经人工核实的抽取结果必须保持 `checked=false`。
