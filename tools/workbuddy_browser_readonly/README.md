# workbuddy_browser_readonly

**状态：`implemented_authorized_local`（本地、只读、需显式授权启用）**

把 WorkBuddy 在**已登录的 BOSS 标签页**上只读提取的结构化内容，接入 `InvestigationAgent`。

## 实际做了什么

1. WorkBuddy 通过浏览器调试协议 **attach 已打开的标签**（不新建标签、不导航、不刷新、不提交表单），读取页面表格的 DOM 文本。
2. 结果以机器可读的 capture bundle 暂存在**授权工作站本地**，不进入公开仓库。
3. `ln_agent.workbuddy_adapters.BrowserSnapshotTool.query("boss:<case>")` 读取这个 bundle，校验后返回 `Fact` 列表。
4. 事实经 `PolicyGuard.validate_facts` → `evidence.evaluate` → `RuleRegistry` → `RiskGate` → `build_disposition`，与离线 fixture 走**完全相同**的链路。

## 边界

- 适配器自身**不联网、不认证、不写回**；`tool.json` 的 `network=false`、`local_only=true`、`writes_external=false` 由 `available_for_call` 运行时校验。
- 只允许 `ln_structured` / `official_primary` 两种 origin；`model_extracted` 或 `reviewer_verified` 由 `PolicyGuard` 拒绝。
- 出生日期 / 证件号 / 注册号含脱敏字符（`*`、`x`、`X`、`•`）时拒绝入库，避免把掩码当成身份级相等。
- 默认 `Policy.allowed_tool_names` **不包含**此工具；仅授权本地运行通过 `authorized_policy()` 显式开启。
- 真实业务数据与完整日志只保存在授权环境，公开仓库里的同名示例是**合成数据**。
