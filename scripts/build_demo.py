"""Build the public, fully synthetic multi-case workbench demo.

The real workbench runs one Case (one screening checklist) at a time. Reviewers
asked for the missing level above it: a checklist-level overview where every
checklist is a card, and clicking one opens its per-hit progress and final
business conclusion. This generator produces that as a single static page.

    python3 scripts/build_demo.py

Outputs:
    examples/demo_workbench_data.json   synthetic case/hit data
    demo.html                           self-contained static demo (no backend)
    index.html                          GitHub Pages entry -> demo.html

`index.html` is owned by this generator; `scripts/build_replay.py` must not
overwrite it (the single-case replay is reachable by link from the demo).

All identifiers, names, domains and reasons are fabricated. The *shape* (8
checklists, 154 hits, 4 workers, ~395 ms per hit, one 88-hit and one 49-hit
checklist) mirrors an authorized local validation run; no real business datum
is included.

v0.9.6 adds the FINAL INDICATOR (最终指标): a deterministic, downstream triage
metric derived from the same rule/evidence outputs.  FI-1 命中 / FI-2 疑似命中 /
FI-3 误报·未命中.  It resolves the business-facing "无结论" bucket for review
priority and statistics, but never rewrites business_conclusion and never
clears or auto-reports a hit.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "examples" / "demo_workbench_data.json"
OUT_HTML = ROOT / "demo.html"
OUT_INDEX = ROOT / "index.html"

# (synthetic case label, subject, entity type, hit count, conclusion mix)
# 严重待核 = business conclusion 无结论, but a serious source-attributed event
# AND a consistent incident location => final indicator 疑似命中 (FI-2).
CASES = [
    ("SYN-LN-2601", "Synth Shipping Holdings Ltd.", "企业", 49,
     {"无法确定": 43, "严重待核": 2, "疑似命中": 3, "未命中": 1, "命中": 0}),
    ("SYN-LN-2602", "合成样例 · 个人主体 A", "个人", 88,
     {"无法确定": 80, "严重待核": 2, "疑似命中": 4, "未命中": 2, "命中": 0}),
    ("SYN-LN-2603", "合成样例 · 个人主体 B", "个人", 10,
     {"无法确定": 7, "严重待核": 1, "疑似命中": 2, "未命中": 0, "命中": 0}),
    ("SYN-LN-2604", "合成样例 · 个人主体 C", "个人", 2,
     {"无法确定": 1, "严重待核": 0, "疑似命中": 0, "未命中": 1, "命中": 0}),
    ("SYN-LN-2605", "合成样例 · 个人主体 D", "个人", 2,
     {"无法确定": 1, "严重待核": 0, "疑似命中": 1, "未命中": 0, "命中": 0}),
    ("SYN-LN-2606", "SynthetIC Semiconductor Co., LIMITED", "企业", 1,
     {"无法确定": 0, "严重待核": 0, "疑似命中": 1, "未命中": 0, "命中": 0}),
    ("SYN-LN-2607", "合成样例 · 企业主体 E", "企业", 1,
     {"无法确定": 0, "严重待核": 0, "疑似命中": 0, "未命中": 0, "命中": 1}),
    ("SYN-LN-2608", "合成样例 · 个人主体 F", "个人", 1,
     {"无法确定": 0, "严重待核": 0, "疑似命中": 0, "未命中": 1, "命中": 0}),
]

BUSINESS_LABELS = ("命中", "疑似命中", "未命中", "无法确定")
INDICATOR_LABELS = ("命中", "疑似命中", "误报·未命中")
INDICATOR_RULES = {"命中": "FI-1", "疑似命中": "FI-2", "误报·未命中": "FI-3"}
REGIONS = ["华东", "华北", "华南", "东北"]

CATEGORIES = ["制裁", "执法", "制裁,执法", "PEP", "不利媒体"]
DOMAINS = [
    "sanctions.example.org", "registry.example.org", "cases.example.org",
    "bulletin.example.org", "media.example.org", "archive.example.org",
]
COMPANY_WORDS = ["Azul", "Boreal", "Cedar", "Delta", "Everest", "Fjord",
                 "Granite", "Harbor", "Ionic", "Juniper", "Kestrel", "Lumen"]
PERSON_WORDS = ["Chen", "Gao", "Li", "Lin", "Liu", "Mei", "Peng", "Shen",
                "Sun", "Wang", "Zhang", "Zhou"]

CONCLUSION_REASONS = {
    "命中": "入网主体与名单记录的完整注册号一致，触发 P08 强关联规则；仍为未经审批的草稿。",
    "未命中": "两侧完整出生日期存在明确冲突，满足授权的排除候选规则；排除依据待复核。",
    "疑似命中": "名称一致且名单事由重大、记录源可追溯；身份关联尚未确认，需人工复核。",
    "无法确定": "证据不足，无法确定是否命中：命中记录未回传证件号/生日，仅提供 LN 内部记录号；记录源原页可达性未核验，无法做证件级比对，不可据此判为未命中。",
    "严重待核": "证据不足，无法确定是否命中：命中记录未回传证件号/生日，仅提供 LN 内部记录号；但名单事由等级为重大，且事发地与入网主体地区一致，按最终指标保留为疑似命中待复核。",
}

INDICATOR_BASIS = {
    "FI-1": ["硬匹配规则命中：DOCUMENT_EXACT_MATCH / COMPANY_REGISTRATION_MATCH",
             "业务结论草稿=命中，identity=strong_link", "命中侧有独立身份字段可比"],
    "FI-2": ["名单事由等级 critical，可引用来源标识 2 条",
             "名单载明事发地与入网主体地区一致（结构化字段精确匹配）",
             "命中侧无可比对独立身份字段（证件号/出生日期/注册号缺失或脱敏）",
             "无确认命中证据，保留疑似命中待复核"],
    "FI-2-report": ["业务结论草稿=疑似命中，report_recommended=True",
                    "名单事由等级 critical，可引用来源标识 2 条",
                    "身份关联尚未确认，保留疑似命中待复核"],
    "FI-3": ["无可引用的重大名单事由（或事发地未形成一致匹配）",
             "命中侧无可比对独立身份字段（证件号/出生日期/注册号缺失或脱敏）",
             "仅通知层信息缺失、无特别信息，按误报归集（不放行）"],
}

STAGES = ["排队", "规则核验", "调查取证", "结论草稿", "已完成"]
# Relative share of one hit's own execution time; absolute values are derived
# per hit so the 5-stage bar always adds up to that hit's measured duration.
STAGE_WEIGHTS = (0.10, 0.24, 0.38, 0.20, 0.08)

# Subject profiling is part of the company_ln / person_ln Skill contracts
# (director, owner, jurisdiction, registration_number, employer, role). The
# WorkBuddy Qichacha connector exposes exactly those fields via
# get_company_profile / get_company_risk_scan / get_executive_risk_scan.
# Values below are fabricated; the field SCHEMA mirrors the connector.
QCC_TOOLS = ["get_company_profile", "get_company_risk_scan", "get_executive_risk_scan"]
INDUSTRIES = ["水上运输业", "批发业", "软件和信息技术服务业",
              "专用设备制造业", "商务服务业", "半导体分立器件制造"]
SCALES = ["微型企业", "小型企业", "中型企业"]


def _profile(ci: int, entity: str, subject: str) -> dict:
    if entity == "企业":
        display = [
            {"label": "企查查行业", "value": INDUSTRIES[ci % len(INDUSTRIES)]},
            {"label": "企业规模", "value": SCALES[ci % len(SCALES)]},
            {"label": "员工人数", "value": f"{9 + ci * 7} 人（合成年报口径）"},
            {"label": "成立日期", "value": f"20{14 + ci:02d}-0{ci % 9 + 1}-18"},
            {"label": "注册资本", "value": f"{20 + ci * 80} 万元"},
            {"label": "经营状态", "value": "存续（合成值）"},
            {"label": "主营产品", "value": "合成业务描述，仅用于展示画像字段"},
            {"label": "统一信用代码", "value": f"SYN-USCC-{ci + 1:04d}"},
        ]
        dimensions, zero = 35, 34 + (ci % 2)
        nonzero = [] if zero == 35 else [{"name": "经营异常", "count": 1}]
        scan_label = "企业 35 项风险因子"
    else:
        display = [
            {"label": "关联企业", "value": f"Synthetic Holdings {ci + 1:02d} Ltd.（合成）"},
            {"label": "任职", "value": ["法定代表人", "股东", "董事", "实际控制人"][ci % 4]},
            {"label": "所在地域", "value": ["华东", "华北", "华南", "东北"][ci % 4] + "（合成）"},
            {"label": "主营方向", "value": INDUSTRIES[(ci + 2) % len(INDUSTRIES)]},
            {"label": "公开履历", "value": "合成公开报道摘要，仅用于展示画像字段"},
            {"label": "企业锚定", "value": subject},
            {"label": "任职企业数", "value": f"{2 + ci} 家（合成工商关联）"},
            {"label": "关系网络", "value": f"关联 {3 + ci * 2} 个主体（合成）"},
        ]
        dimensions, zero = 18, 17 + (ci % 2)
        nonzero = [] if zero == 18 else [{"name": "裁判文书", "count": 2}]
        scan_label = "个人 18 项风险因子"
    return {
        "connector": "WorkBuddy 企查查连接器",
        "tools": QCC_TOOLS,
        "synthetic": True,
        "note": "字段结构来自企查查连接器；本页所有取值均为合成演示值，未发起实时查询。",
        "display": display,
        "risk_scan": {
            "label": scan_label,
            "dimensions": dimensions,
            "zero_hit": zero,
            "nonzero": nonzero,
        },
    }


def _reason(conclusion: str, domain: str, ln_id: str) -> str:
    base = CONCLUSION_REASONS[conclusion]
    return (f"{base} 记录源主域名 {domain}；"
            f"命中侧 LN 记录号 {ln_id}（非证件号）。")


# ---------------------------------------------------------------------------
# v0.9.7: plain-language explanations.
#
# Reviewers said the old per-hit text was machine vocabulary (status codes,
# rule ids, source domains) and never answered "how was this hit confirmed?"
# or "how were the others excluded?".  These fields are DISPLAY ONLY: they
# describe the already-computed conclusion, they never change it.  The rule
# engine, PolicyGuard, Decision Router, Disposition and FI-1/2/3 are untouched.
# ---------------------------------------------------------------------------

def _explanation(*, bucket: str, entity: str, name: str, subject: str,
                 domain: str, ln_id: str, category: str, region: str,
                 subject_region: str, severity: str, serious: bool,
                 location_ok: bool, source_count: int, ci: int, n: int) -> dict:
    """Build a human-readable, field-by-field account of ONE hit."""
    reg = f"SYN-USCC-{ci + 1:04d}"
    doc = f"SYN-DOC-{ci + 1:04d}-{n:03d}"
    dob = f"19{60 + (ci * 7 + n) % 35:02d}-0{(ci + n) % 9 + 1}-{(n * 3) % 27 + 1:02d}"
    other_year = 40 + (ci * 5 + n) % 19   # 1940-1958, never overlaps dob (1960+)
    other_dob = f"19{other_year:02d}-0{(ci * 3 + n) % 9 + 1}-{(n * 7) % 27 + 1:02d}"
    assert other_dob != dob
    name_field = "企业名称" if entity == "企业" else "姓名"
    id_field = "企业注册号" if entity == "企业" else "证件号码"
    date_field = "成立日期" if entity == "企业" else "出生日期"
    id_value = reg if entity == "企业" else doc
    compare: list[dict] = []
    evidence = f"来自 {domain} 等 {source_count} 条名单记录源，名单记录号 {ln_id}"

    if bucket == "命中":
        headline = f"判定为命中：{name_field}对上了，更关键的是{id_field}完全一致，可以确认是同一个主体。"
        compare = [
            {"field": name_field, "subject": subject,
             "list": f"{name}（按名称规则与入网主体匹配）",
             "result": "名称匹配", "note": "名字对上只说明被名单捞出来，不能定性"},
            {"field": id_field, "subject": id_value, "list": id_value,
             "result": "完全一致", "note": "这是唯一标识，编号一致才算同一主体"},
            {"field": date_field, "subject": dob, "list": dob,
             "result": "一致", "note": "交叉印证，不是主要依据"},
            {"field": "所在地区", "subject": subject_region, "list": subject_region,
             "result": "一致", "note": "辅助信息，地区相同不能单独定性"},
        ]
        why = (f"系统先把入网主体的 {id_field}（{id_value}）与名单记录里的编号逐一比对，"
               f"两者一字不差；再核对名称、日期、地区，也没有出现冲突。"
               f"唯一标识一致且没有反证，所以规则判定为「命中」。")
        why_not = (f"没有判为「未命中」，是因为{id_field}、{date_field}都没有出现冲突"
                   f"（名称相同、地址相同只是辅助信息，真正定案的是唯一标识）；"
                   f"也没有判为「疑似命中」，因为不需要再补证件信息就能确认。")
        next_step = "请复核名单原文与主体证件，确认编号不是录入错误；这是草稿，需授权人员审批后才生效，不会自动上报或放行。"
    elif bucket == "未命中":
        headline = f"判定为未命中（排除候选）：名字虽然撞上了，但{date_field}明确不同，不可能是同一个主体。"
        compare = [
            {"field": name_field, "subject": subject,
             "list": f"{name}（按名称规则与入网主体匹配）",
             "result": "名称匹配", "note": "这就是被名单捞出来的原因"},
            {"field": date_field, "subject": dob, "list": other_dob,
             "result": "明确冲突", "note": f"同一个主体的{date_field}不可能有两个"},
            {"field": id_field, "subject": id_value, "list": "名单侧未回传",
             "result": "无法比对", "note": "因此排除依据是日期冲突，不是证件号"},
            {"field": "名单事由", "subject": "—", "list": f"{category}·{severity}",
             "result": "已记录", "note": "事由不改变身份判断"},
        ]
        why = (f"入网主体的{date_field}是 {dob}，名单记录写的是 {other_dob}，两者明确冲突；"
               f"这属于硬身份字段，冲突即可作为排除候选。"
               f"换句话说：这条是「同名不同主体」。")
        why_not = (f"没有判为「命中」，因为{id_field}没有形成一致匹配，且{date_field}明确冲突；"
                   f"最终指标归到「误报·未命中」只是统计与复核优先级口径，"
                   f"不是系统判它「没有风险」。这同样不是「放行」：命中记录没有被清除，"
                   f"排除要由授权人员确认。")
        next_step = f"请人工核对名单原件里的{date_field}是否为录入错误；确认无误后才可走排除审批，系统不会自动清除这条命中。"
    elif bucket in ("疑似命中", "严重待核"):
        headline = (("业务结论仍留空、但复核优先级提高：名字对上了、名单事由重大且事发地一致，"
                     f"可名单侧没给{id_field}，无法确认是不是同一个主体。")
                    if bucket == "严重待核" else
                    "判定为疑似命中草稿：名字对上了、名单事由重大且事发地一致，"
                    f"但名单侧没给{id_field}，无法确认是不是同一个主体。")
        compare = [
            {"field": name_field, "subject": subject,
             "list": f"{name}（按名称规则与入网主体匹配）",
             "result": "名称匹配", "note": "只说明撞名，不说明同人"},
            {"field": id_field, "subject": id_value, "list": "名单侧未回传",
             "result": "无法比对", "note": "缺唯一标识，不能确认同一主体"},
            {"field": date_field, "subject": dob, "list": "名单侧未回传",
             "result": "无法比对", "note": "缺硬身份字段"},
            {"field": "事发地 / 主体地区", "subject": subject_region, "list": region,
             "result": "一致", "note": "结构化字段精确匹配，不是模型猜的"},
            {"field": "名单事由", "subject": "—", "list": f"{category}·重大（有来源标识）",
             "result": "重大", "note": "有可引用来源，不能当普通误报放掉"},
        ]
        why = (f"能唯一识别主体的{id_field}、{date_field}，名单这条记录都没有回传；"
               f"但名单事由等级为重大、有来源标识，且名单载明的事发地（{region}）"
               f"与入网主体地区（{subject_region}）精确一致。"
               f"两个条件同时成立时，即使业务上还下不了结论，复核优先级也要提高。")
        why_not = (f"没有判为「命中」，因为没有任何唯一标识匹配；"
                   f"也没有归到「误报」，因为事由重大且事发地一致，不能只凭「没给证件号」就放掉。"
                   f"这同样不是「放行」：命中记录没有被清除，排除要由授权人员确认。"
                   + ("业务结论仍然留空，只是最终指标把它提到疑似命中。" if bucket == "严重待核" else ""))
        next_step = (f"请打开名单原页/通知附件补取{id_field}或{date_field}，"
                     f"取到后重新做证件级比对；在此之前不得放行或上报。")
    else:  # 无法确定 -> 误报·未命中
        headline = (f"按误报归集：只是名字撞上了，名单侧没有能唯一识别主体的"
                    f"{id_field}/{date_field}，也没有重大事由，"
                    f"找不到能证明是同一个主体的证据。")
        compare = [
            {"field": name_field, "subject": subject,
             "list": f"{name}（按名称规则与入网主体匹配）",
             "result": "名称匹配", "note": "被名单捞出来的唯一原因，重名很常见"},
            {"field": id_field, "subject": id_value, "list": "名单侧未回传",
             "result": "无法比对", "note": "名单只给了内部记录号，不是证件号"},
            {"field": date_field, "subject": dob, "list": "名单侧未回传",
             "result": "无法比对", "note": "缺硬身份字段"},
            {"field": "名单侧其他编号", "subject": "—",
             "list": f"仅内部记录号 {ln_id}",
             "result": "无法比对", "note": "内部记录号不是证件号，不能拿来认人"},
            {"field": "事发地", "subject": subject_region,
             "list": region if location_ok else "名单未载明 / 不一致",
             "result": "一致" if location_ok else "未形成一致匹配",
             "note": "缺值按未知处理，绝不靠模型推断"},
            {"field": "名单事由", "subject": "—",
             "list": f"{category}·{severity}",
             "result": "未构成重大事由", "note": "分类存在，但没有可引用的重大风险事件"},
        ]
        why = (f"系统能比的唯一标识（{id_field}、{date_field}）名单这条记录一条都没给，"
               f"只有 {ln_id} 这样的内部记录号；记录原页也没有核验到更细的身份信息。"
               f"同时名单事由不重大、事发地没有形成一致匹配，"
               f"所以没有任何证据能说明名单里的主体和入网主体是同一个。")
        why_not = (f"这不是「放行」也不是「白名单」：命中记录没有被清除，LN 工单状态不变，"
                   f"只是把这条的复核优先级放低、计入统计口径。"
                   f"如果后续从通知附件拿到{id_field}或{date_field}，必须重新做证件级比对。")
        next_step = (f"批量核查时这类可先低优先级处理；抽查时请回名单原页确认通知附件里"
                     f"是否含{id_field}或{date_field}，有则重新比对。")

    return {
        "tag": f"{category} · {domain} · 名单记录 {ln_id}",
        "headline": headline,
        "compare": compare,
        "why": why,
        "why_not": why_not,
        "next_step": next_step,
        "evidence": evidence,
        "caveat": "以上为未经审批的结论草稿；系统不自动放行、不清除命中、不自动发送报告。",
    }


HOW_TO_READ = [
    {"label": "命中", "color": "hit",
     "text": "唯一标识（企业注册号 / 证件号 / 出生日期）两侧完全一致，且没有冲突字段 → 确认是同一主体。光是名字一样不算。"},
    {"label": "疑似命中", "color": "susp",
     "text": "名字对上了、事由重大、事发地一致，但名单侧缺证件信息 → 既不能确认也不能排除，留给人复核。"},
    {"label": "误报·未命中", "color": "clear",
     "text": "只有名字撞上了，名单侧没给证件号 / 生日 / 注册号，也没有重大事由 → 没有证据说是同一个人，先放低复核优先级。不是放行、不是白名单，命中记录仍保留。"},
    {"label": "为什么大批量的都能归到误报", "color": "unk",
     "text": "名单命中的触发条件通常只是「名字相同或相近」。真正能定人的是唯一标识；名单通知里往往只有内部记录号，没有证件级信息。逐条能核对的结论就是「查不到能证明同人的证据」，这属于证据不足的归集，不是逐条判定无风险。"},
]


def _indicator(bucket: str, region: str, domain: str, ln_id: str) -> dict:
    """Mirror ln_agent.final_indicator.FI-1/2/3 on synthetic demo data."""
    if bucket == "命中":
        label, rule, basis_key = "命中", "FI-1", "FI-1"
    elif bucket == "严重待核":
        label, rule, basis_key = "疑似命中", "FI-2", "FI-2"
    elif bucket == "疑似命中":
        label, rule, basis_key = "疑似命中", "FI-2", "FI-2-report"
    else:
        label, rule, basis_key = "误报·未命中", "FI-3", "FI-3"
    serious = bucket in ("疑似命中", "严重待核")
    basis = list(INDICATOR_BASIS[basis_key])
    basis.append(f"记录源主域名 {domain}；命中侧 LN 记录号 {ln_id}（非证件号）")
    return {
        "final_indicator": label,
        "final_indicator_rule": rule,
        "final_indicator_basis": basis,
        "final_indicator_status": "DRAFT_NOT_APPROVED",
        "indicator_does_not_clear_hit": True,
        "indicator_changes_business_conclusion": False,
        "severity": "critical" if serious else "medium",
        "event_region": region if serious else "未知",
        "subject_region": region,
        "location_consistent": serious,
        "identity_fields_available": bucket == "命中",
    }


def build() -> dict:
    cases = []
    for ci, (cid, subject, entity, count, mix) in enumerate(CASES):
        labels = [c for c, n in mix.items() for _ in range(n)]
        # Spread the rare outcomes across the checklist so the first 25 rows
        # already show a mix of final indicators instead of 25 identical rows.
        major = [c for c in labels if c == "无法确定"]
        rare = [c for c in labels if c != "无法确定"]
        spread: list[str] = []
        for i, bucket in enumerate(major):
            spread.append(bucket)
            if rare and (i + 1) % 7 == 0:
                spread.append(rare.pop(0))
        spread.extend(rare)
        labels = spread
        assert len(labels) == count, (cid, len(labels), count)
        hits = []
        for i in range(count):
            n = i + 1
            bucket = labels[i]
            # 严重待核 still has NO business conclusion; only the derived
            # final indicator changes (FI-2). Keep the two axes separate.
            conclusion = "无法确定" if bucket == "严重待核" else bucket
            domain = DOMAINS[(ci * 3 + i) % len(DOMAINS)]
            category = CATEGORIES[(ci * 5 + i * 3) % len(CATEGORIES)]
            score = 100 if i % 17 else 99
            ln_id = f"7{ci}{i:03d}0{n:02d}"
            region = REGIONS[(ci + i) % len(REGIONS)]
            indicator = _indicator(bucket, region, domain, ln_id)
            if entity == "企业":
                name = f"Synthetic {COMPANY_WORDS[i % len(COMPANY_WORDS)]} " \
                       f"Trading {ci + 1:02d}-{n:02d} Co., Ltd."
            else:
                name = f"{PERSON_WORDS[i % len(PERSON_WORDS)]}, " \
                       f"{PERSON_WORDS[(i + 5) % len(PERSON_WORDS)]} {ci + 1:02d}-{n:02d}"
            # A single hit really costs ~395 ms of engine work in the authorized
            # run (HIT_FINISHED.duration_ms). The 103 ms figure seen elsewhere is
            # the WALL-CLOCK share after 4 workers, not the duration of one hit.
            duration = round(372 + ((ci * 7 + i * 11) % 47) + (6 if count > 40 else 0), 1)
            path = ["EVALUATE", "INVESTIGATE · workbuddy_browser_readonly",
                    "EVALUATE", "RESIDUAL_SUSPICION" if conclusion == "无法确定" else "WRITE_DISPOSITION"]
            if conclusion == "疑似命中":
                path.insert(3, "INVESTIGATE · workbuddy_llm_capture")
            path_cn = ["比对入网主体与名单记录的身份字段",
                       "只读打开名单原页，找证件号 / 生日 / 注册号",
                       "把取到的字段放回规则引擎再比一次",
                       "写出结论草稿（不发送、不放行）"]
            serious = bucket in ("疑似命中", "严重待核")
            explanation = _explanation(
                bucket=bucket, entity=entity, name=name, subject=subject,
                domain=domain, ln_id=ln_id, category=category, region=region,
                subject_region=region, severity=indicator["severity"],
                serious=serious, location_ok=indicator["location_consistent"],
                source_count=3 + (i % 8), ci=ci, n=n)
            hits.append({
                "hit_id": f"SYN-H{n:03d}",
                "name": name,
                "entity_type": entity,
                "category": category,
                "ln_score": score,
                "ln_id": ln_id,
                "source_domain": domain,
                "conclusion": conclusion,
                "conclusion_status": "DRAFT_NOT_APPROVED" if conclusion != "无法确定" else "NO_CONCLUSION",
                "duration_ms": duration,
                "reason": _reason(bucket, domain, ln_id),
                "explanation": explanation,
                "path_cn": path_cn,
                "stages": STAGES,
                "stage_ms": [round(duration * w, 1) for w in STAGE_WEIGHTS],
                "path": path,
                "source_count": 3 + (i % 8),
                **indicator,
            })
        dist = {c: sum(1 for h in hits if h["conclusion"] == c) for c in BUSINESS_LABELS}
        dist = {c: v for c, v in dist.items() if v}
        ind_dist = {c: sum(1 for h in hits if h["final_indicator"] == c)
                    for c in INDICATOR_LABELS}
        case_indicator = max((c for c in INDICATOR_LABELS if ind_dist[c]),
                             key=lambda c: {"误报·未命中": 1, "疑似命中": 2, "命中": 3}[c],
                             default="误报·未命中")
        escalation = ind_dist["命中"] + ind_dist["疑似命中"]
        # engine_ms is the SUM of this case's per-hit work (no parallelism yet).
        # wall_ms is that same case after its own 4 workers split the hits.
        # The two must never be divided by each other a second time.
        engine_ms = round(sum(h["duration_ms"] for h in hits), 1)
        wall_ms = round(engine_ms / 4, 1)
        cases.append({
            "case_id": cid,
            "subject": subject,
            "entity_type": entity,
            "hit_count": count,
            "workers": 4,
            "engine_ms": engine_ms,
            "wall_ms": wall_ms,
            "speedup": round(engine_ms / wall_ms, 2) if wall_ms else 1.0,
            "mean_ms_per_hit": round(engine_ms / count, 1),
            "conclusion_distribution": dist,
            "final_indicator": case_indicator,
            "final_indicator_distribution": ind_dist,
            "escalation_hits": escalation,
            "escalation_rate": round(escalation / count, 4) if count else 0.0,
            "profile": _profile(ci, entity, subject),
            "hits": hits,
        })
    total_hits = sum(c["hit_count"] for c in cases)
    dist = {k: sum(c["conclusion_distribution"].get(k, 0) for c in cases)
            for k in BUSINESS_LABELS}
    ind_total = {k: sum(c["final_indicator_distribution"][k] for c in cases)
                 for k in INDICATOR_LABELS}
    escalation_total = ind_total["命中"] + ind_total["疑似命中"]
    engine_total = round(sum(c["engine_ms"] for c in cases), 1)
    wall_serial = round(sum(c["wall_ms"] for c in cases), 1)
    wall_together = max(c["wall_ms"] for c in cases)
    wall_shared = round(engine_total / 4, 1)
    return {
        "schema": "ln-agent-demo-workbench/1.3",
        "how_to_read": HOW_TO_READ,
        "disclaimer": "SYNTHETIC ONLY — 所有工单号、主体、命中记录、域名与说明均为虚构；仅复现授权本地验证的运行形态与量级，不含任何真实业务数据。",
        "generated_by": "scripts/build_demo.py",
        "note": "本页按『工单主体 → 点进去 → 每条命中进度与最终结论』组织。每条命中同时展示『业务结论草稿』与『最终指标』两个轴；最终指标是派生统计口径，不改变业务结论、不自动放行。并发模型：8 个工单主体同时开始、互不干扰，每个主体内部再由 4 个 worker 并行处理自己的命中；静态版无需 Python 后端。",
        "final_indicator": {
            "name": "最终指标",
            "kind": "TRIAGE_METRIC",
            "labels": list(INDICATOR_LABELS),
            "rules": {
                "FI-1": "命中：证件号 / 企业注册号 / 出生日期硬匹配，或业务结论草稿已确认命中（strong_link）。",
                "FI-2": "疑似命中：名单事由重大（high/critical 且有来源标识）且事发地与主体/记录所在地一致；或已有上报草稿、政策要求升级、来源冲突/工具阻断（这些不得归入误报）。",
                "FI-3": "误报·未命中：无特别信息——例如命中侧根本拿不到只有通知里才有的身份信息，且无重大事由或事发地不一致。按误报归集，仅作复核优先级与统计口径。",
            },
            "boundary": "最终指标是 Rule Engine → PolicyGuard → Decision Router → Disposition 之后的下游派生指标；不改变业务结论、不改写 business_conclusion / recommendation / route，不自动放行、清除命中、发送报告，也不因信息不足创建人工调查任务。工具阻断与来源冲突一律保留为疑似命中。",
            "metric": "需人工复核率 =（命中 + 疑似命中）/ 全部命中记录",
            "escalation_hits": escalation_total,
            "escalation_rate": round(escalation_total / total_hits, 4),
            "distribution": ind_total,
        },
        "concurrency": {
            "model": "m 个工单主体同时开始，每个主体内部 4 workers 按命中并行",
            "cases_start_together": True,
            "workers_per_case": 4,
            "total_workers_if_isolated": 4 * len(cases),
            "wall_ms_all_cases_together": wall_together,
            "wall_ms_shared_pool": wall_shared,
            "wall_ms_serial_cases": wall_serial,
            "why_not_one_hit": (
                "单条命中约 395 ms 是它自己的引擎工作量，不是整批完成时间。"
                "并发度有限：154 条命中在共享 4-worker 池上至少要 154/4≈39 轮；"
                "8 个主体同时开跑、每单各 4 workers（共 32 并发）时，"
                "总墙钟由最慢的那张工单决定，仍然远大于 1 条命中的耗时。"
            ),
            "authorized_run_note": (
                "授权本地实测是逐单运行（8 张工单一前一后），累计墙钟约 15.9 s；"
                "本页展示的是 8 个主体同时开跑的理想并发视图，两者口径不同。"
            ),
        },
        "totals": {
            "cases": len(cases),
            "hits": total_hits,
            "workers": 4,
            "engine_ms": engine_total,
            "wall_ms": wall_together,
            "wall_ms_shared_pool": wall_shared,
            "wall_ms_serial_cases": wall_serial,
            "mean_ms_per_hit": round(engine_total / total_hits, 1),
            "mean_wall_ms_per_hit": round(wall_serial / total_hits, 1),
            "total_workers_if_isolated": 4 * len(cases),
            "conclusion_distribution": dist,
            "final_indicator_distribution": ind_total,
            "escalation_hits": escalation_total,
            "escalation_rate": round(escalation_total / total_hits, 4),
            "largest_case_hits": max(c["hit_count"] for c in cases),
        },
        "cases": cases,
    }


def _assert_synthetic(payload: dict) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    for marker in ("LN20", "sk-", "ghp_", "yeepay", "boss.", "merchantNo"):
        if marker in blob:
            raise RuntimeError(f"refusing to publish demo: found marker {marker!r}")
    if re.search(r"(?<!\d)\d{15,18}(?!\d)", blob):
        raise RuntimeError("refusing to publish demo: document-sized number")
    if payload["totals"]["hits"] != 154 or payload["totals"]["cases"] != 8:
        raise RuntimeError("demo shape drifted from the validated run")
    ind = payload["totals"]["final_indicator_distribution"]
    if sum(ind.values()) != payload["totals"]["hits"]:
        raise RuntimeError("final indicator distribution does not sum to hit count")
    if len(payload["how_to_read"]) != 4:
        raise RuntimeError("plain-language 'how to read' panel is incomplete")
    for case in payload["cases"]:
        if sum(case["final_indicator_distribution"].values()) != case["hit_count"]:
            raise RuntimeError("case-level final indicator distribution drifted")
        for hit in case["hits"]:
            if hit["final_indicator"] not in payload["final_indicator"]["labels"]:
                raise RuntimeError("unknown final indicator label")
            if not hit["indicator_does_not_clear_hit"]:
                raise RuntimeError("final indicator must never clear a hit")
            ex = hit["explanation"]
            if len(ex["compare"]) < 4 or not all(
                    k in ex and ex[k] for k in
                    ("headline", "why", "why_not", "next_step", "evidence", "caveat")):
                raise RuntimeError("per-hit plain-language explanation is incomplete")
            if "不是「放行」" not in ex["why_not"] and hit["final_indicator"] == "误报·未命中":
                raise RuntimeError("false-positive bucket must state it is not a clearance")


INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=demo.html">
<title>LN 筛查 Agent · 核验工作台 Demo</title>
</head>
<body>
<p>正在打开 <a href="demo.html">多工单核验工作台 Demo</a>…</p>
<p>另可查看 <a href="replay.html">单次执行事件回放</a>，或 <a href="demo.html?autorun=1">打开即自动运行 Demo</a>。</p>
</body>
</html>
"""

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LN 筛查 Agent · 核验工作台 Demo</title>
<style>
:root{--bg:#f4f6fa;--panel:#fff;--panel2:#f8fafc;--border:#e2e8f0;--text:#16202e;--muted:#6b7a8d;--accent:#2563eb;--accent2:#eff5ff;--shadow:0 1px 3px rgba(20,35,60,.07);--hit:#d93b3b;--susp:#d98514;--clear:#177a55;--unk:#7b8798}
html[data-theme="dark"]{--bg:#10151d;--panel:#1a212c;--panel2:#151c25;--border:#2b3645;--text:#e8eef7;--muted:#9aa9bc;--accent:#7ea9ff;--accent2:#1c2a41;--shadow:0 1px 3px rgba(0,0,0,.3);--hit:#ff8b8b;--susp:#f0bd68;--clear:#69d3a5;--unk:#a9b6c8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1240px;margin:0 auto;padding:24px 22px 60px}
header.top{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap;margin-bottom:16px}
h1{font-size:24px;margin:0 0 7px;letter-spacing:-.3px}
.sub{color:var(--muted);margin:0;max-width:820px;font-size:13px}
.badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:11px}
.badge{font-size:11.5px;padding:3px 9px;border-radius:999px;background:var(--accent2);color:var(--accent);border:1px solid var(--border)}
.badge.g{background:#e8f7f0;color:#137a4d}html[data-theme="dark"] .badge.g{background:#17342a;color:#7ce0b2}
.btn{border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:8px;padding:8px 13px;cursor:pointer;font-size:13px;box-shadow:var(--shadow)}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.btn.primary:hover{opacity:.9;color:#fff}
.btn:disabled{opacity:.55;cursor:default}
.kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin:16px 0}
.kpi{background:var(--panel);border:1px solid var(--border);border-radius:11px;padding:13px 15px;box-shadow:var(--shadow)}
.kpi b{display:block;font-size:23px;letter-spacing:-.5px;line-height:1.25}
.kpi span{color:var(--muted);font-size:12px}
.stack{display:flex;height:7px;border-radius:99px;overflow:hidden;background:var(--border);margin:9px 0 7px}
.stack i{display:block;height:100%}
.c-hit{background:var(--hit)}.c-susp{background:var(--susp)}.c-clear{background:var(--clear)}.c-unk{background:var(--unk)}
.fi-hit{background:var(--hit)}.fi-susp{background:var(--susp)}.fi-fp{background:var(--clear)}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:var(--muted)}
.legend b{font-weight:600;color:var(--text)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}
.section-title{font-size:15px;margin:22px 0 12px;display:flex;justify-content:space-between;align-items:center;gap:10px}
.section-title small{font-weight:400;color:var(--muted);font-size:12px}
.cases{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.case{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:15px;cursor:pointer;box-shadow:var(--shadow);transition:.15s;position:relative;overflow:hidden}
.case:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:0 8px 22px rgba(30,60,110,.12)}
.case .cid{font-size:11.5px;color:var(--accent);font-weight:700;letter-spacing:.3px}
.case .subject{font-size:13px;font-weight:600;margin:5px 0 9px;min-height:38px;word-break:break-word}
.case .big{font-size:27px;font-weight:700;letter-spacing:-.6px;line-height:1.15}
.case .big em{font-style:normal;font-size:12px;font-weight:500;color:var(--muted);margin-left:5px}
.case .row{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted);margin-top:8px}
.case .foot{display:flex;justify-content:space-between;align-items:center;margin-top:11px;padding-top:9px;border-top:1px dashed var(--border);font-size:11.5px;color:var(--muted)}
.case .go{color:var(--accent);font-weight:600}
.case .progress{position:absolute;left:0;bottom:0;height:3px;background:var(--accent);width:0;transition:width .25s}
.pill{font-size:11px;border-radius:5px;padding:2px 7px;border:1px solid var(--border);white-space:nowrap}
.p-hit{background:rgba(217,59,59,.11);color:var(--hit);border-color:transparent}
.p-susp{background:rgba(217,133,20,.13);color:var(--susp);border-color:transparent}
.p-clear{background:rgba(23,122,85,.11);color:var(--clear);border-color:transparent}
.p-unk{background:rgba(123,135,152,.13);color:var(--unk);border-color:transparent}
.p-fi-hit{background:rgba(217,59,59,.12);color:var(--hit);border-color:transparent;font-weight:700}
.p-fi-susp{background:rgba(217,133,20,.15);color:var(--susp);border-color:transparent;font-weight:700}
.p-fi-fp{background:rgba(23,122,85,.13);color:var(--clear);border-color:transparent;font-weight:700}
.final-panel{background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--susp);border-radius:12px;padding:15px 17px;margin:0 0 18px;box-shadow:var(--shadow)}
.final-panel h2{font-size:15px;margin:0 0 4px}
.final-panel .lead{color:var(--muted);font-size:12.5px;margin:0 0 12px}
.fi-top{display:grid;grid-template-columns:170px minmax(0,1fr);gap:16px;align-items:center}
.fi-metric{background:var(--accent2);border:1px solid var(--border);border-radius:10px;padding:10px 12px;text-align:center}
.fi-metric b{display:block;font-size:27px;line-height:1.2;color:var(--accent);letter-spacing:-.6px}
.fi-metric span{font-size:11.5px;color:var(--muted)}
.fi-rules{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}
.fi-rules div{background:var(--panel2);border:1px solid var(--border);border-radius:8px;padding:9px 11px;font-size:11.8px;color:var(--muted);line-height:1.55}
.fi-rules b{display:block;color:var(--text);font-size:12.3px;margin-bottom:3px}
.fi-bound{font-size:11.5px;color:var(--muted);margin-top:11px;border-top:1px dashed var(--border);padding-top:9px}
.ind-line{font-size:11.5px;color:var(--muted);margin-top:6px}
.ind-line b{color:var(--text)}
.hit .basis{margin-top:8px;font-size:11.8px;color:var(--muted);line-height:1.6}
.hit .basis i{font-style:normal;display:inline-block;background:var(--panel2);border:1px solid var(--border);border-radius:5px;padding:2px 6px;margin:2px 4px 0 0}
.chip{font-size:11px;background:var(--panel2);border:1px solid var(--border);border-radius:6px;padding:2px 7px;color:var(--muted)}
.detail{display:none}
.detail.on{display:block}
.home.off{display:none}
.crumb{display:flex;align-items:center;gap:10px;margin-bottom:14px;font-size:13px;color:var(--muted)}
.hero{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow);margin-bottom:14px}
.hero h2{margin:0 0 4px;font-size:19px}
.hero .meta{color:var(--muted);font-size:12.5px}
.hero-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px}
.hero-grid div{background:var(--panel2);border:1px solid var(--border);border-radius:8px;padding:9px 11px}
.hero-grid b{display:block;font-size:17px}
.hero-grid span{font-size:11.5px;color:var(--muted)}
.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;background:var(--panel)}
.seg button{border:0;background:transparent;color:var(--muted);padding:6px 11px;cursor:pointer;font-size:12px;border-right:1px solid var(--border)}
.seg button:last-child{border-right:0}
.seg button.on{background:var(--accent2);color:var(--accent);font-weight:600}
.search{border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:8px;padding:7px 11px;font-size:12.5px;min-width:190px}
.hit{background:var(--panel);border:1px solid var(--border);border-radius:9px;padding:11px 13px;margin-bottom:7px;cursor:pointer;box-shadow:var(--shadow)}
.hit:hover{border-color:var(--accent)}
.hit .r1{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.hit .idx{color:var(--muted);font-size:11.5px;min-width:44px;font-variant-numeric:tabular-nums}
.hit .nm{font-weight:600;font-size:13px;flex:1;min-width:180px;word-break:break-word}
.hit .r2{display:grid;grid-template-columns:minmax(0,1fr) 82px 96px;gap:12px;align-items:center;margin-top:8px}
.steps{display:flex;gap:3px}
.steps i{flex:1;height:5px;border-radius:3px;background:var(--border);transition:background .2s}
.steps i.on{background:var(--accent)}
.hit .phase{font-size:11.5px;color:var(--muted);white-space:nowrap}
.hit .ms{font-size:11.5px;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.hit .reason{display:none;margin-top:10px;padding-top:9px;border-top:1px dashed var(--border);font-size:12.5px;color:var(--muted)}
.hit.open .reason{display:block}
.hit .reason b{color:var(--text)}
.hit .path{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}
/* v0.9.7 plain-language explanation */
.howto{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 16px;margin-bottom:14px;box-shadow:var(--shadow)}
.howto h2{font-size:15px;margin:0 0 4px}
.howto .lead{font-size:12.3px;color:var(--muted);margin:0 0 11px}
.howto-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.howto-grid>div{background:var(--panel2);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:9px 11px;font-size:12px;line-height:1.62;color:var(--muted)}
.howto-grid>div b{display:block;color:var(--text);font-size:12.5px;margin-bottom:2px}
.howto-grid>div.c-hit{border-left-color:var(--hit)}.howto-grid>div.c-susp{border-left-color:var(--susp)}
.howto-grid>div.c-clear{border-left-color:var(--clear)}.howto-grid>div.c-unk{border-left-color:var(--unk)}
.ex-tag{font-size:11.3px;color:var(--muted);margin:2px 0 5px}
.ex-head{font-size:13.5px;line-height:1.65;color:var(--text);font-weight:600;background:var(--accent2);border-radius:8px;padding:9px 11px;margin:2px 0 10px}
.ex-q{font-size:12.5px;line-height:1.72;margin:9px 0;color:var(--muted)}
.ex-q b{color:var(--text)}
.cmp{width:100%;border-collapse:collapse;margin:8px 0 4px;font-size:12px}
.cmp th{background:var(--panel2);border:1px solid var(--border);padding:6px 8px;text-align:left;color:var(--muted);font-weight:600;white-space:nowrap}
.cmp td{border:1px solid var(--border);padding:6px 8px;vertical-align:top;word-break:break-word}
.cmp td:first-child{white-space:nowrap;color:var(--text);font-weight:600}
.cmp .r-ok{color:var(--clear);font-weight:600}.cmp .r-bad{color:var(--hit);font-weight:600}
.cmp .r-miss{color:var(--muted);font-weight:600}
.cmp .small{display:block;color:var(--muted);font-size:11.3px;margin-top:2px;line-height:1.5}
.ex-warn{font-size:12px;color:var(--muted);border-left:3px solid var(--susp);padding-left:9px;margin:10px 0 0;line-height:1.65}
.ex-tech{margin-top:11px;border-top:1px dashed var(--border);padding-top:8px}
.ex-tech summary{cursor:pointer;font-size:12px;color:var(--accent)}
.ex-tech .techbody{font-size:11.8px;color:var(--muted);line-height:1.7;margin-top:8px}
.ex-tech .techbody b{color:var(--text)}
.ex-steps{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}
.ex-steps i{font-style:normal;font-size:11.3px;background:var(--panel2);border:1px solid var(--border);border-radius:5px;padding:2px 7px;color:var(--muted)}
.hit .path i{font-style:normal;font-size:11px;background:var(--accent2);color:var(--accent);border-radius:5px;padding:2px 7px}
.more{display:block;width:100%;margin-top:10px}
.profile{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 16px;margin-bottom:14px;box-shadow:var(--shadow)}
.profile h3{font-size:14px;margin:0 0 4px;display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}
.profile .src{font-size:11.5px;color:var(--muted);margin-bottom:11px}
.profile .fields{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.profile .fields div{background:var(--panel2);border:1px solid var(--border);border-radius:7px;padding:7px 9px}
.profile .fields span{display:block;font-size:11px;color:var(--muted)}
.profile .fields b{font-size:12.5px;font-weight:600;word-break:break-word}
.profile .scan{margin-top:10px;font-size:12px;color:var(--muted);border-top:1px dashed var(--border);padding-top:9px}
.profile .scan b{color:var(--text)}
.notice{background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:11px 14px;color:var(--muted);font-size:12.5px;margin-top:18px}
.notice p{margin:9px 0 0}.notice .fine{font-size:11.5px;opacity:.85}
.cmodels{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:11px}
.cmodels div{background:var(--panel2);border:1px solid var(--border);border-radius:8px;padding:9px 11px}
.cmodels b{display:block;font-size:12px;color:var(--text)}
.cmodels span{font-size:11.5px;color:var(--muted)}
footer{margin-top:24px;color:var(--muted);font-size:12.5px;display:flex;gap:16px;flex-wrap:wrap}
@media(max-width:1050px){.cases{grid-template-columns:repeat(2,1fr)}.kpis{grid-template-columns:repeat(3,1fr)}}
@media(max-width:620px){.cases{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}.hero-grid{grid-template-columns:repeat(2,1fr)}.hit .r2{grid-template-columns:1fr 70px}}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div>
    <h1>LN 筛查 Agent · 核验工作台 Demo</h1>
    <p class="sub">按<strong>工单主体</strong>组织：每张卡片是一张核查单，点进去看这条工单里<strong>每一条命中的处理进度、业务结论草稿与最终指标</strong>。<strong>最终指标</strong>把「无结论」按规则归到 <b>命中 / 疑似命中 / 误报·未命中</b>，并给出全批唯一的汇总指标。<strong>8 个工单主体同时开始、互不干扰</strong>，每个主体内部再由 4 个 worker 并行处理自己的命中；点「运行一遍 Demo」可看这一层并发，也可用 <code>?autorun=1</code> 打开即自动运行。本页为静态单文件，无需后端、无需登录、全部为合成数据。</p>
    <div class="badges"><span class="badge">8 个主体同时开跑</span><span class="badge">154 条命中</span><span class="badge">每单 4 workers · 共 32 并发</span><span class="badge">含最终指标与企查查主体画像</span><span class="badge g">零外部请求</span><span class="badge">全部合成数据</span></div>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <button class="btn primary" id="runall">▶ 运行一遍 Demo</button>
    <button class="btn" id="theme">切换深色</button>
    <a class="btn" href="examples/demo_workbench_data.json" download>下载数据</a>
    <a class="btn" href="README.md">项目说明</a>
  </div>
</header>

<div id="home" class="home">
  <div class="kpis" id="kpis"></div>
  <div class="howto" id="howto"></div>
  <div class="final-panel" id="finalPanel"></div>
  <div class="section-title">工单主体总览 <small>点击任一工单查看逐条命中 · 大批量命中单（88 / 49 条）同样在此</small></div>
  <div class="cases" id="cases"></div>
  <div class="notice" id="scaleNote"></div>
</div>

<div id="detail" class="detail">
  <div class="crumb"><button class="btn" id="back">← 返回工单总览</button><span id="crumbText"></span></div>
  <div class="hero" id="hero"></div>
  <div class="profile" id="profile"></div>
  <div class="toolbar">
    <button class="btn primary" id="runcase">▶ 运行本工单</button>
    <div class="seg" id="filter"></div>
    <input class="search" id="search" placeholder="搜索命中名称 / 来源域名">
    <span style="font-size:12px;color:var(--muted)" id="shown"></span>
  </div>
  <div id="hits"></div>
  <button class="btn more" id="more">加载更多命中</button>
</div>

<footer>
  <a href="https://github.com/Lkjhgfdsa-mnbvcxz/ln-screening-agent">GitHub 仓库</a>
  <a href="replay.html">单次执行回放</a>
  <a href="docs/WORKBENCH.md">工作台与 SSE 接口说明</a>
  <span>真实项目运行：<code>python3 run.py web</code> → <code>http://127.0.0.1:8765</code></span>
</footer>
</div>

<script type="application/json" id="demo-data">__DEMO_DATA__</script>
<script>
(function(){
 "use strict";
 const D=JSON.parse(document.getElementById("demo-data").textContent);
 const $=id=>document.getElementById(id);
 const esc=s=>String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
 const COLORS={"命中":"c-hit","疑似命中":"c-susp","未命中":"c-clear","无法确定":"c-unk"};
 const PILL={"命中":"p-hit","疑似命中":"p-susp","未命中":"p-clear","无法确定":"p-unk"};
 const ORDER=["命中","疑似命中","未命中","无法确定"];
 const IND_ORDER=["命中","疑似命中","误报·未命中"];
 const IND_COLORS={"命中":"fi-hit","疑似命中":"fi-susp","误报·未命中":"fi-fp"};
 const IND_PILL={"命中":"p-fi-hit","疑似命中":"p-fi-susp","误报·未命中":"p-fi-fp"};
 const IND_CLASS={"命中":"c-hit","疑似命中":"c-susp","误报·未命中":"c-clear"};
 let current=null, filter="全部", query="", shown=25, running=false, timers=[];

 function stack(dist){
   const total=IND_ORDER.reduce((a,k)=>a+(dist[k]||0),0)||1;
   return `<div class="stack">${IND_ORDER.filter(k=>dist[k]).map(k=>`<i class="${IND_COLORS[k]}" style="width:${dist[k]/total*100}%"></i>`).join("")}</div>`;
 }
 function legend(dist){
   return `<div class="legend">${IND_ORDER.filter(k=>dist[k]).map(k=>`<span><i class="dot ${IND_COLORS[k]}"></i><b>${dist[k]}</b> ${k}</span>`).join("")}</div>`;
 }
 function renderHowto(){
   $("howto").innerHTML=`<h2>这一批是怎么判的 · 先看这里</h2>
     <p class="lead">名单命中通常只因为「名字一样」。真正能定人的是证件号 / 出生日期 / 企业注册号。下面四句话解释全部 ${D.totals.hits} 条命中的归类逻辑；点开任一工单、再点开单条命中，可以看到这一条具体比了哪些字段。</p>
     <div class="howto-grid">${(D.how_to_read||[]).map(x=>`<div class="c-${esc(x.color)}"><b>${esc(x.label)}</b>${esc(x.text)}</div>`).join("")}</div>`;
 }
 function renderKpis(){
   const t=D.totals, cc=D.concurrency;
   $("kpis").innerHTML=[
     [t.cases,"工单主体（同时开跑）"],[t.hits,"命中记录"],
     [t.mean_ms_per_hit.toFixed(0)+" ms","单条命中实际耗时"],
     [(t.wall_ms/1000).toFixed(1)+" s","8 主体同时开跑 · 总墙钟"],
     [t.total_workers_if_isolated,"总并发 workers"],
     [(t.escalation_rate*100).toFixed(1)+"%","最终指标 · 需人工复核率"]
   ].map(([v,k])=>`<div class="kpi"><b>${esc(v)}</b><span>${esc(k)}</span></div>`).join("");
   const F=D.final_indicator, id=t.final_indicator_distribution;
   $("finalPanel").innerHTML=`<h2>最终指标 · 全批唯一汇总</h2>
     <p class="lead">每条命中都会得到一个明确的最终指标，不再停留在「无结论」。${esc(F.metric)}；本批 <b>${t.escalation_hits}</b> 条需要人工复核，占 <b>${(t.escalation_rate*100).toFixed(1)}%</b>。</p>
     <div class="fi-top">
       <div class="fi-metric"><b>${(t.escalation_rate*100).toFixed(1)}%</b><span>需人工复核率<br>${t.escalation_hits} / ${t.hits} 条</span></div>
       <div>${stack(id)}${legend(id)}<div class="ind-line">业务结论草稿仍单独保留：${ORDER.filter(k=>t.conclusion_distribution[k]).map(k=>`<b>${t.conclusion_distribution[k]}</b> ${esc(k)}`).join(" · ")}</div></div>
     </div>
     <div class="fi-rules">
       <div><b>FI-1 命中</b>${esc(F.rules["FI-1"])}</div>
       <div><b>FI-2 疑似命中</b>${esc(F.rules["FI-2"])}</div>
       <div><b>FI-3 误报·未命中</b>${esc(F.rules["FI-3"])}</div>
     </div>
     <div class="fi-bound">${esc(F.boundary)}</div>`;
   const big=D.cases.reduce((a,b)=>a.hit_count>b.hit_count?a:b);
   $("scaleNote").innerHTML=`<strong>并发模型：m 个工单主体一起干、互不干扰。</strong>
     8 个主体<b>同时开始</b>，每个主体内部把命中切给 <b>4 个 worker</b>（共 ${t.total_workers_if_isolated} 并发），
     各自走同一套 Rule Engine → PolicyGuard → Investigation → Disposition 链路，完成一条就显示一条。
     <b>总墙钟由最慢的那张单决定</b>：${big.case_id} 有 ${big.hit_count} 条命中，
     本单墙钟 ${big.wall_ms.toFixed(0)} ms，因此整批约 <b>${t.wall_ms.toFixed(0)} ms</b>。
     <div class="cmodels">
       <div><b>8 单同时开跑 · 每单 4 workers</b><span>${t.wall_ms.toFixed(0)} ms · 本页演示口径</span></div>
       <div><b>全局共享 4-worker 池</b><span>${t.wall_ms_shared_pool.toFixed(0)} ms · 并发度不变</span></div>
       <div><b>授权本地实测 · 逐单运行</b><span>${t.wall_ms_serial_cases.toFixed(0)} ms · 累计墙钟</span></div>
     </div>
     <p><strong>为什么不是「1 条命中的时间跑完 154 条」？</strong>单条命中实际约
     <b>${t.mean_ms_per_hit.toFixed(0)} ms</b>，而 <b>${t.mean_wall_ms_per_hit.toFixed(0)} ms/命中</b>
     只是并行后摊到每条的墙钟份额，两者都<b>不是整批完成时间</b>。并发度有限：共享 4-worker 池时
     154 条命中至少要 154/4≈39 轮；把 worker 数提到 ≥154 才可能接近单条耗时，那不是当前配置。
     ${esc(cc.why_not_one_hit)}</p>
     <p class="fine">${esc(cc.authorized_run_note)} 详情列表默认先渲染 25 条，可继续加载。</p>`;
 }
 function renderCases(){
   $("cases").innerHTML=D.cases.map((c,i)=>`
     <div class="case" data-i="${i}">
       <div class="cid">${esc(c.case_id)} <span class="chip">${esc(c.entity_type)}</span> <span class="chip">含主体画像</span></div>
       <div class="subject">${esc(c.subject)}</div>
       <div class="big">${c.hit_count}<em>条命中</em></div>
       ${stack(c.final_indicator_distribution)}
       ${legend(c.final_indicator_distribution)}
       <div class="ind-line">工单最终指标 <span class="pill ${IND_PILL[c.final_indicator]}">${esc(c.final_indicator)}</span> · 需复核 ${c.escalation_hits} 条（${(c.escalation_rate*100).toFixed(1)}%）</div>
       <div class="row"><span>本单墙钟 ${c.wall_ms.toFixed(0)} ms</span><span>单条 ${c.mean_ms_per_hit.toFixed(0)} ms · ${c.speedup.toFixed(1)}x</span></div>
       <div class="foot"><span class="pill p-clear">已完成 · 结论草稿</span><span class="go">点进去查看 →</span></div>
       <div class="progress"></div>
     </div>`).join("");
   $("cases").addEventListener("click",e=>{
     const card=e.target.closest(".case"); if(!card) return;
     location.hash=D.cases[+card.dataset.i].case_id;
     openCase(+card.dataset.i);
   });
 }
 function openCase(i){
   stopTimers(); current=D.cases[i]; filter="全部"; query=""; shown=25;
   $("home").classList.add("off"); $("detail").classList.add("on");
   $("crumbText").textContent=`${current.case_id} · ${current.subject}`;
   window.scrollTo(0,0);
   const c=current;
   $("hero").innerHTML=`<h2>${esc(c.case_id)} · ${esc(c.subject)}</h2>
     <div class="meta">${esc(c.entity_type)}主体 · ${c.hit_count} 条 LN 命中 · 本单 4 workers（加速 ${c.speedup.toFixed(1)}x）· 与其他 7 个主体同时开跑 · 所有结论均为未经审批的草稿</div>
     <div class="hero-grid">
       <div><b>${c.hit_count}</b><span>命中记录</span></div>
       <div><b>${c.engine_ms.toFixed(0)} ms</b><span>单条耗时之和（未并行）</span></div>
       <div><b>${c.wall_ms.toFixed(0)} ms</b><span>本单 4 workers 墙钟</span></div>
       <div><b>${c.mean_ms_per_hit.toFixed(0)} ms</b><span>单条命中实际耗时</span></div>
     </div>${stack(c.final_indicator_distribution)}${legend(c.final_indicator_distribution)}
     <div class="ind-line">工单最终指标 <span class="pill ${IND_PILL[c.final_indicator]}">${esc(c.final_indicator)}</span> · 需人工复核 <b>${c.escalation_hits}</b> / ${c.hit_count} 条（${(c.escalation_rate*100).toFixed(1)}%）· 业务结论草稿：${ORDER.filter(k=>c.conclusion_distribution[k]).map(k=>`<b>${c.conclusion_distribution[k]}</b> ${esc(k)}`).join(" · ")}</div>`;
   const p=c.profile;
   $("profile").innerHTML=`<h3>主体画像 · ${esc(c.entity_type)}主体
       <span class="pill p-clear">${esc(p.connector)} · 字段结构</span></h3>
     <div class="src">${esc(p.note)}　连接器工具：${p.tools.map(esc).join(" / ")}</div>
     <div class="fields">${p.display.map(f=>`<div><span>${esc(f.label)}</span><b>${esc(f.value)}</b></div>`).join("")}</div>
     <div class="scan"><b>${esc(p.risk_scan.label)}</b>：共 ${p.risk_scan.dimensions} 项维度，${p.risk_scan.zero_hit} 项 0 命中${p.risk_scan.nonzero.length?"；有记录："+p.risk_scan.nonzero.map(x=>esc(x.name)+" "+x.count+" 条").join("、"):"；全部维度 0 命中"}。<b>0 命中仅代表结构化维度当前无记录，不等于主体无风险</b>（连接器口径，须并行核对舆情）。</div>`;
   $("filter").innerHTML=["全部",...IND_ORDER].map(k=>`<button data-k="${k}" class="${k==="全部"?"on":""}">按最终指标：${k}</button>`).join("");
   $("search").value="";
   renderHits(true);
 }
 $("back").onclick=()=>{stopTimers();history.replaceState(null,"",location.pathname+location.search);$("detail").classList.remove("on");$("home").classList.remove("off");window.scrollTo(0,0);};
 $("filter").addEventListener("click",e=>{
   const b=e.target.closest("button"); if(!b)return;
   filter=b.dataset.k; [...$("filter").children].forEach(x=>x.classList.toggle("on",x===b));
   shown=25; renderHits(true);
 });
 $("search").oninput=e=>{query=e.target.value.trim().toLowerCase();shown=25;renderHits(true);};
 $("more").onclick=()=>{shown+=25;renderHits(false);};

 function visibleHits(){
   return current.hits.filter(h=>(filter==="全部"||h.final_indicator===filter)&&
     (!query||(h.name+" "+h.source_domain+" "+h.hit_id+" "+h.conclusion+" "+h.final_indicator).toLowerCase().includes(query)));
 }
 function renderHits(reset){
   if(reset) $("hits").innerHTML="";
   const all=visibleHits(), slice=all.slice(0,shown);
   $("shown").textContent=`显示 ${Math.min(shown,all.length)} / ${all.length} 条`+
     (filter!=="全部"?" · 已筛选":"");
   $("more").style.display=shown<all.length?"block":"none";
   $("more").textContent=`加载更多命中（还有 ${Math.max(0,all.length-shown)} 条）`;
   // re-render whole visible slice to keep progress state readable
   $("hits").innerHTML=slice.map((h,i)=>`
     <div class="hit" data-key="${esc(h.hit_id)}" data-p="${esc(h.path.join("|"))}">
       <div class="r1">
         <span class="idx">#${String(i+1).padStart(2,"0")}</span>
         <span class="nm">${esc(h.name)}</span>
         <span class="chip">${esc(h.category)}</span>
         <span class="chip">分数 ${h.ln_score}</span>
         <span class="chip">业务结论 ${esc(h.conclusion)}</span>
         <span class="pill ${IND_PILL[h.final_indicator]}">最终指标 ${esc(h.final_indicator)}</span>
       </div>
       <div class="r2">
         <div><div class="steps">${h.stages.map(()=>"<i></i>").join("")}</div>
              <div class="phase">已完成 · ${esc(h.path[h.path.length-1])}</div></div>
         <span class="phase">${esc(h.source_domain)}</span>
         <span class="ms" title="这条命中自己的引擎耗时，不是整批完成时间">${h.duration_ms.toFixed(1)} ms</span>
       </div>
       <div class="reason">
         <div class="ex-tag">${esc(h.explanation.tag)}</div>
         <div class="ex-head">${esc(h.explanation.headline)}</div>
         <div class="ex-q"><b>比了哪些字段：</b></div>
         <table class="cmp"><thead><tr><th>比对项</th><th>入网主体</th><th>名单记录</th><th>结果</th></tr></thead><tbody>
           ${h.explanation.compare.map(c=>{
             const cls=/一致/.test(c.result)&&!/不一致|未形成/.test(c.result)?"r-ok":(/冲突/.test(c.result)?"r-bad":"r-miss");
             return `<tr><td>${esc(c.field)}</td><td>${esc(c.subject)}</td><td>${esc(c.list)}</td><td class="${cls}">${esc(c.result)}<span class="small">${esc(c.note)}</span></td></tr>`;
           }).join("")}
         </tbody></table>
         <div class="ex-q"><b>为什么这么判：</b>${esc(h.explanation.why)}</div>
         <div class="ex-q"><b>为什么不是别的结论：</b>${esc(h.explanation.why_not)}</div>
         <div class="ex-q"><b>复核人下一步做什么：</b>${esc(h.explanation.next_step)}</div>
         <div class="ex-q"><b>证据来源：</b>${esc(h.explanation.evidence)}</div>
         <div class="ex-warn">${esc(h.explanation.caveat)}</div>
         <div class="ex-q"><b>这条走了哪几步：</b>
           <div class="ex-steps">${h.path_cn.map(p=>`<i>${esc(p)}</i>`).join("")}</div></div>
         <details class="ex-tech"><summary>查看技术字段与执行路径（给开发 / 审计看）</summary>
           <div class="techbody">
             <b>业务结论草稿：</b>${esc(h.conclusion)}（${esc(h.conclusion_status)}）·
             <b>最终指标：</b>${esc(h.final_indicator)}（${esc(h.final_indicator_rule)}，${esc(h.final_indicator_status)}）<br>
             <b>名单事由等级：</b>${esc(h.severity)} · <b>事发地：</b>${esc(h.event_region)} / 主体 ${esc(h.subject_region)} ·
             <b>事发地一致：</b>${h.location_consistent?"是":"否"}<br>
             <b>指标依据：</b><div class="basis">${h.final_indicator_basis.map(x=>`<i>${esc(x)}</i>`).join("")}</div>
             <b>原始核查说明：</b>${esc(h.reason)}<br>
             <b>来源：</b>${esc(h.source_domain)} 等 ${h.source_count} 条记录源 · LN 记录号 ${esc(h.ln_id)}
             <div class="path">${h.path.map(p=>`<i>${esc(p)}</i>`).join("")}</div>
           </div>
         </details>
       </div>
     </div>`).join("");
   [...$("hits").querySelectorAll(".steps")].forEach(el=>el.querySelectorAll("i").forEach(i=>i.classList.add("on")));
 }
 $("hits").addEventListener("click",e=>{
   const row=e.target.closest(".hit"); if(row) row.classList.toggle("open");
 });
 function stopTimers(){timers.forEach(clearTimeout);timers=[];running=false;$("runall").disabled=false;$("runcase").disabled=false;$("runall").textContent="▶ 运行一遍 Demo";$("runcase").textContent="▶ 运行本工单";}
 function animate(){
   if(running)return; running=true; timers.forEach(clearTimeout); timers=[];
   $("runall").disabled=true;$("runcase").disabled=true;
   $("runall").textContent="运行中…";$("runcase").textContent="运行中…";
   const cards=[...$("cases").children];
   // All m checklist subjects start at t=0 and never block each other. Each
   // card's animation length is proportional to that case's own wall clock,
   // so the slowest case finishes last and the fast ones finish earlier.
   const span=2600, maxWall=Math.max(...D.cases.map(c=>c.wall_ms));
   cards.forEach(card=>{card.querySelector(".progress").style.width="0%";});
   cards.forEach((card,i)=>{
     const total=Math.max(420,span*(D.cases[i].wall_ms/maxWall));
     for(let s=1;s<=10;s++){
       timers.push(setTimeout(()=>{card.querySelector(".progress").style.width=(s*10)+"%";},total/10*s));
     }
   });
   timers.push(setTimeout(()=>{
     cards.forEach(c=>{const f=c.querySelector(".foot .pill"); if(f){f.textContent="已完成 · 结论草稿";}});
     stopTimers();
   },span+120));
   if($("detail").classList.contains("on")) runDetail();
 }
 function runDetail(){
   const rows=[...$("hits").querySelectorAll(".hit")];
   rows.forEach(r=>r.querySelectorAll(".steps i").forEach(i=>i.classList.remove("on")));
   rows.forEach((row,idx)=>{
     // 4 workers => 4 hits progress in the same wave, not one after another.
     const wave=Math.floor(idx/4);
     for(let s=1;s<=5;s++){
       timers.push(setTimeout(()=>{
         const bars=row.querySelectorAll(".steps i");
         for(let k=0;k<s;k++) if(bars[k]) bars[k].classList.add("on");
         const ph=row.querySelector(".phase"); if(ph) ph.textContent=["排队中","规则核验","调查取证","结论草稿","已完成"][s-1];
       },60+wave*180+s*70));
     }
   });
 }
 $("runall").onclick=animate;
 $("runcase").onclick=()=>{
   if(running)return; running=true; timers.forEach(clearTimeout);timers=[];
   $("runcase").disabled=true;$("runcase").textContent="运行中…";
   runDetail();
   const last=60+Math.ceil(Math.min(shown,visibleHits().length)/4)*180+5*70;
   timers.push(setTimeout(stopTimers,last+150));
 };
 $("theme").onclick=()=>{
   const dark=document.documentElement.dataset.theme==="dark";
   document.documentElement.dataset.theme=dark?"light":"dark";
   $("theme").textContent=dark?"切换深色":"切换浅色";
 };
 renderHowto();renderKpis();renderCases();
 // Deep link: demo.html#SYN-LN-2602 opens that checklist directly, useful for
 // sharing a large-hit example and for documentation screenshots.
 const wanted=decodeURIComponent(location.hash.replace(/^#/,""));
 const at=D.cases.findIndex(c=>c.case_id===wanted);
 if(at>=0) openCase(at);
 // One-click link for reviewers: ?autorun=1 starts the parallel simulation as
 // soon as the page opens (optionally combined with a case hash).
 if(new URLSearchParams(location.search).get("autorun")==="1"){
   timers.push(setTimeout(animate,350));
 }
})();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate only, do not write")
    args = ap.parse_args()
    payload = build()
    _assert_synthetic(payload)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if args.check:
        print(f"synthetic OK: {payload['totals']['cases']} cases, "
              f"{payload['totals']['hits']} hits, {len(data)} bytes")
        return
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    OUT_HTML.write_text(HTML.replace("__DEMO_DATA__", data.replace("</", "<\\/")),
                        encoding="utf-8")
    OUT_INDEX.write_text(INDEX_HTML, encoding="utf-8")
    print(f"wrote {OUT_JSON.relative_to(ROOT)} ({OUT_JSON.stat().st_size} bytes)")
    print(f"wrote {OUT_HTML.relative_to(ROOT)} ({OUT_HTML.stat().st_size} bytes)")
    print(f"wrote {OUT_INDEX.relative_to(ROOT)} ({OUT_INDEX.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
