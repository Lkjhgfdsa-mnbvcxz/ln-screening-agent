"""Plain-language, DISPLAY-ONLY explanation of one already-decided hit.

v0.9.7.  Reviewers could not read the workbench output: it showed status
codes, rule ids and source domains, but never answered "what exactly was
compared?", "why is this a hit?" or "how were the others excluded?".

This module builds a human-readable account strictly from values that the
deterministic chain ALREADY produced.  It:

  * reads only subject/hit facts, evidence rule findings and the final
    disposition labels;
  * never calls a model, a tool or an external source;
  * never produces a Fact, never sets ``checked``, never adds evidence;
  * never changes ``business_conclusion`` / ``recommendation`` / ``route`` /
    rule findings / gate / FI labels.

The output is attached to ``Decision.disposition['plain_summary']`` after every
decision field is final.  PolicyGuard validates the display-only flags.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .evidence import norm
from .models import EvidenceResult, Hit, Subject

KIND = "DISPLAY_ONLY"

RULE_CN = {
    "DOCUMENT_EXACT_MATCH": "证件号码完全一致",
    "COMPANY_REGISTRATION_MATCH": "企业注册号完全一致",
    "DOB_EXACT_MATCH": "出生日期完全一致",
    "DOB_EXACT_CONFLICT": "出生日期明确冲突",
    "PRE_BIRTH_ACTION_IMPOSSIBLE": "名单记载的行为早于主体出生，不可能成立",
    "DOCUMENT_DIFFERENCE_NEEDS_HISTORY_VERIFICATION": "证件号码存在差异，需核实证件历史",
}

# field -> (Chinese label, applicable entity types)
_FIELDS = (
    ("company_name", "企业名称", ("company",)),
    ("name", "姓名", ("person", "address")),
    ("document_number", "证件号码", ("person",)),
    ("registration_number", "企业注册号", ("company",)),
    ("dob", "出生日期", ("person",)),
    ("address", "地址", ("person", "company", "address")),
    ("region", "所在地区", ("person", "company", "address")),
)

_MASK_CHARS = set("*xX•")


# v0.9.6 wrote a few raw field ids into the indicator basis. The display
# layer translates them so a reviewer never has to decode `dob`.
_HUMAN_TOKENS = {
    "dob": "出生日期", "document_number": "证件号码",
    "registration_number": "企业注册号", "source_ref": "来源标识",
    "DOCUMENT_EXACT_MATCH": "证件号完全一致",
    "COMPANY_REGISTRATION_MATCH": "企业注册号完全一致",
    "DOB_EXACT_MATCH": "出生日期完全一致",
    "DOB_EXACT_CONFLICT": "出生日期明确冲突",
}


def _clean(value: Any, limit: int = 120) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _humanize(value: str) -> str:
    for token, label in _HUMAN_TOKENS.items():
        value = re.sub(rf"(?<![A-Za-z_]){re.escape(token)}(?![A-Za-z_])", label, value)
    return value


def _masked(value: str) -> bool:
    v = value.strip()
    return not v or all(c in _MASK_CHARS or c.isspace() for c in v)


def _fact(facts: Iterable[Any], field: str):
    return next((f for f in facts if getattr(f, "field", "") == field
                 and getattr(f, "value", "") not in (None, "")), None)


def _compare_rows(subject: Subject, hit: Hit, hit_facts: list) -> list[dict]:
    rows: list[dict] = []
    for field, label, applies in _FIELDS:
        if hit.entity_type not in applies:
            continue
        a, b = _fact(subject.facts, field), _fact(hit_facts, field)
        if not a and not b:
            continue
        av = _clean(getattr(a, "value", "")) if a else "入网侧未提供"
        bv = _clean(getattr(b, "value", "")) if b else "名单侧未回传"
        if a and b and _masked(av) and _masked(bv):
            result, note = "脱敏", "脱敏值不参与硬相等或冲突判断"
        elif a and b and (_masked(av) or _masked(bv)):
            result, note = "无法比对", "有一侧是脱敏值，不能拿来认人"
        elif a and b:
            same = norm(av) == norm(bv)
            result = "一致" if same else "明确冲突"
            note = ("两侧取值相同" if same else
                    "同一个主体的这个字段不可能有两个值")
        else:
            result = "无法比对"
            note = "名单只给了内部记录号，没有这个字段" if not b else "入网申请里没有这个字段"
        rows.append({"field": label, "subject": av, "list": bv,
                     "result": result, "note": note})
    return rows


def _rule_captions(evidence: EvidenceResult) -> tuple[list[str], list[str]]:
    linked = [RULE_CN.get(r, r) for r in evidence.linked_rules]
    excluded = [RULE_CN.get(r, r) for r in evidence.exclusion_rules]
    return linked, excluded


def build_plain_summary(*, subject: Subject, hit: Hit,
                        evidence: EvidenceResult, identity: str,
                        business_conclusion: str | None,
                        final_indicator: str, final_indicator_rule: str,
                        final_indicator_basis: list[str],
                        recommendation: str, report_recommended: bool,
                        hit_facts: list, source_refs: list[str]) -> dict:
    """Describe an existing decision in Chinese. Never decides anything."""
    rows = _compare_rows(subject, hit, hit_facts)
    linked, excluded = _rule_captions(evidence)
    hard_fields = {"企业注册号", "证件号码", "出生日期"}
    id_label = ("企业注册号" if hit.entity_type == "company"
                else "证件号码、出生日期")
    matched = [r for r in rows if r["result"] == "一致" and r["field"] in hard_fields]
    conflicts = [r for r in rows if r["result"] == "明确冲突"]
    hard_conflicts = [r for r in conflicts if r["field"] in hard_fields]
    soft_conflicts = [r for r in conflicts if r["field"] not in hard_fields]
    comparable = [r for r in rows if r["result"] in ("一致", "明确冲突")]
    # Address/region values change over time: they are context, never a hard
    # exclusion. Saying "no conflict" while showing a red conflict row is the
    # exact kind of machine-speak reviewers complained about.
    soft_note = ("；" + "、".join(r["field"] for r in soft_conflicts)
                 + "虽然不同，但这类字段会变动、不能用来认人，不构成排除依据"
                 if soft_conflicts else "")
    basis_text = ("；".join(_humanize(_clean(x, 90)) for x in final_indicator_basis
                           if _clean(x)) or "依据见技术字段")
    axis_note = ("另外，最终指标是「" + final_indicator + "」，它只是复核优先级口径，"
                 "不改写上面的业务结论、也不清除命中：" + basis_text + "。")

    if business_conclusion == "命中":
        headline = ("判定为命中：能唯一识别主体的编号两侧完全一致，"
                    "可以确认名单里的主体就是入网主体。")
        why = ("规则引擎先比对了" + id_label + "这类唯一标识，结果"
               + ("是「" + "、".join(r["field"] for r in matched) + "」完全一致" if matched
                  else "存在强关联硬匹配")
               + ("；触发的规则是" + "、".join(linked) + "。" if linked else "。")
               + "名字相同只是把这条记录捞出来，真正定案的是唯一标识。")
        why_not = ("没有判为「未命中」，是因为唯一标识没有任何冲突，"
                   "也没有硬排除规则成立"
                   + (soft_note if soft_note else "（例如出生日期不同、证件号不同）")
                   + "；也不必再补证件信息，所以不是「疑似命中」。")
        next_step = ("请复核名单原文与主体证件，确认编号不是录入错误；"
                     "这是草稿，需授权人员审批后才生效，不会自动上报或放行。")
    elif business_conclusion == "未命中":
        decisive = hard_conflicts or conflicts
        headline = ("判定为未命中（排除候选）：名字虽然撞上了，"
                    "但能唯一识别主体的字段明确冲突，不可能是同一个主体。")
        why = ("入网主体与名单记录在"
               + ("、".join(r["field"] for r in decisive) if decisive else "硬身份字段")
               + "上取值不同："
               + "；".join(f"{r['field']} 入网是 {r['subject']}、名单是 {r['list']}"
                          for r in decisive[:2])
               + "。这属于硬排除规则（"
               + ("、".join(excluded) if excluded else "字段冲突") + "），即「同名不同主体」"
               + soft_note + "。")
        why_not = ("没有判为「命中」，因为缺少一致的唯一标识；"
                   "这同样不是「放行」：命中记录没有被清除，排除要由授权人员确认。")
        if final_indicator != "误报·未命中":
            why_not += axis_note
        next_step = ("请人工核对名单原件里的冲突字段是否为录入错误；"
                     "确认无误后才可走排除审批，系统不会自动清除这条命中。")
    elif business_conclusion == "疑似命中":
        headline = ("判定为疑似命中草稿：有值得上报的风险线索，"
                    "但缺少能确认同一主体的证件级证据。")
        why = ("名字对上了，且"
               + ("存在可引用的名单事由、" if report_recommended else "")
               + "现有证据不足以做唯一标识匹配（"
               + ("、".join(linked) if linked else "没有硬匹配规则命中") + "）。"
               + "因此不能确认命中，也不能排除，保留给人工复核。")
        why_not = ("没有判为「命中」，因为没有任何唯一标识一致；"
                   "也没有判为「未命中」，因为没有硬身份字段的明确冲突"
                   + soft_note
                   + "，不能只凭「信息不足」就放掉。")
        next_step = (f"请打开名单原页/通知附件补取{id_label}，"
                     f"取到后重新做证件级比对；在此之前不得放行或自动发送。")
    else:
        headline = ("业务上暂不下结论：能唯一识别主体的字段名单侧没有回传，"
                    "现有证据无法确认也无法排除。")
        why = ("系统能比的唯一标识（" + id_label + "）名单侧都没给，"
               "只有名单内部记录号；已核对的字段里"
               + (f"有 {len(comparable)} 项可比、其余缺失或脱敏。" if comparable
                  else "没有可比对的身份字段。")
               + "最终指标把它归为「" + final_indicator + "」（"
               + final_indicator_rule + "），用于复核优先级与统计："
               + basis_text + "。")
        why_not = ("这不是「放行」也不是「白名单」：命中记录没有被清除，"
                   "LN 工单状态与业务结论草稿都不变，只是复核优先级放低。"
                   + ("本条还存在工具或政策阻断，不能归到误报。" if "阻断" in basis_text else "")
                   + f"如果后续从通知附件拿到{id_label}，必须重新做证件级比对。")
        next_step = ("批量核查时这类可按最终指标排优先级；抽查时请回名单原页确认"
                     f"通知附件里是否含{id_label}，有则重新比对。")

    return {
        "kind": KIND,
        "headline": headline,
        "compare": rows,
        "why": why,
        "why_not": why_not,
        "next_step": next_step,
        "evidence": ("可追溯来源：" + "、".join(_clean(x, 90) for x in source_refs[:4])
                     if source_refs else "本条没有可引用的来源标识"),
        "caveat": "以上为未经审批的结论草稿；系统不自动放行、不清除命中、不自动发送报告。",
        "changes_business_conclusion": False,
        "adds_evidence": False,
        "clears_hit": False,
        "generated_by": "ln_agent/plain_language.py",
    }
