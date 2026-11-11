"""Contract for optional LLM extractor integration. No API call in this prototype."""
from __future__ import annotations
from .models import Fact

SYSTEM_INSTRUCTION = """只从输入中抽取明确陈述的可核验事实；不得推断年龄、职业历程、身份、籍贯。
必须返回 JSON 列表，字段：side, field, value, evidence_id, origin, checked, context, source_url。
所有由模型抽取的事实 origin 必须是 model_extracted，checked 必须为 false；
检查可靠性及原文引用应由独立来源验证器完成。不得直接输出误报、命中、上报决定。"""

def validate_extraction(payload: list[dict]) -> list[Fact]:
    result = []
    for item in payload:
        data = dict(item)
        data["origin"] = "model_extracted"
        data["checked"] = False
        result.append(Fact.from_dict(data))
    return result
