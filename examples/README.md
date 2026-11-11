# Synthetic examples

All cases and documents in this directory are fabricated for offline regression and demonstrations. **Do not substitute real merchant records in a public repository.**

- `case_true_link.json`: synthetic strong-identity-link case; still requires risk review.
- `case_false_positive.json`: synthetic credible DOB difference; exclusion candidate, not authorized clearance.
- `demo_case.json` + `research_fixtures.json`: multi-hit routing fixture.
- `document_case.json` + `document_manifest.json` + `documents/`: local document parsing fixture.

Generate the paired report from the repository root:

```bash
python3 run.py demo --out examples/two_case_demo_report.json
```

Generated `*_report.json` outputs are ignored by Git to avoid committing runtime artifacts.

## 两个合成疑似命中场景（V0.8）

- `case_company_critical_suspected.json`：企业名称一致、同类型注册地址不同；严重事件有显式来源标识，但身份仍未确定。
- `case_person_identity_suspected.json`：姓名、生日、完整证件号一致，居住地址不同，附合成重大执法事由来源标识。

执行 `python3 -m scripts.run_disposition_demo`。**完全虚构，不代表已核验的真实商户或监管事实**。
