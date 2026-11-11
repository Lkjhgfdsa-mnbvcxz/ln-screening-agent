# Git 上传、分享与安全审查

## 首先确认公开范围

**推荐先建立 private 仓库**，经公司允许后再决定是否公开。仓库不应出现内部 SOP 截图、真实商户入网材料、身份证/护照、案件查询结果、客户姓名、交易记录、LN/BOSS 账号、Cookies、API keys 或公司内部 URL。此 ZIP 仅包含合成案例；原 WorkBuddy 设计文档没有放入公开就绪源码，以免混入内部业务案例。

## 本地运行（Mac）

```bash
python3 --version             # 需要 Python >=3.10
python3 run_two_cases.py
python3 -m unittest discover -s tests -v
```

## 建 Git 仓库（在本项目 README 所在目录执行）

```bash
git init -b main
git status --short
git add .
git commit -m "Initial integrated offline LN screening agent prototype"
```

在 GitHub/GitLab 网页端先新建空仓库，复制真实仓库地址；然后：

```bash
git remote add origin <YOUR_REAL_REPOSITORY_URL>
git push -u origin main
```

若远程已有提交（README、license 等），先同步而非强制推送；不要把令牌粘贴在命令行参数中或提交进文件。上传完成后，用浏览器打开仓库页面 URL 分享给 WorkBuddy。不能凭空生成分享链接；必须实际创建并推送远程仓库。

## 公开前排查

```bash
git status --short
git diff --cached --stat
git ls-files
# 使用 secret scanner（例如 gitleaks），并手工检查材料来源与合规发布权限。
```

仓库默认通过 `.gitignore` 排除 `.env`、数据库文件、缓存、日志与生成报告。`.gitignore` 不能代替人工审查或阻止已被追踪的敏感数据。
