# Scripts

从仓库根目录运行：

| 命令 | 用途 |
|---|---|
| `python3 run.py demo` | 最简单双案例演示（推荐） |
| `python3 -m scripts.run_two_cases` | 对两个合成案例执行断言 |
| `python3 -m scripts.run_disposition_demo` | 输出内部简短说明和上报草稿 |
| `python3 -m scripts.run_documents examples/document_case.json examples/document_manifest.json` | 演示本地文件解析与证据定位 |

历史版本 V0.4/V0.5 的单独演示脚本已移除；相应验证继续由 `tests/test_verification.py` 和 `tests/test_v05.py` 覆盖。
