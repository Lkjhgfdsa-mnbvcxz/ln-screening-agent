"""Skills are query guidance, not approval policies or permission grants."""
from __future__ import annotations
SKILLS = {
    "person": {
        "id": "PERSON_CHECK_V0.2",
        "fields": ["name", "dob", "document_number", "gender", "employer", "role", "acted_in_year", "address", "pep_status", "photo_comparison", "event_recency", "region", "company_name"],
        "preferred_sources": ["ln", "official", "doc", "web", "qcc"],
        "allowed_research_sources": ["ln", "official", "doc", "web", "qcc"],
        "blocked_exclusion_fields": ["region", "address", "business_region", "photo_comparison", "pep_status", "role", "employer"],
        "prohibited_shortcuts": ["职位推定出生年份", "跨省居住即排除", "服刑且存在公司即排除", "仅凭人脸照片自动排除"],
    },
    "company": {
        "id": "COMPANY_CHECK_V0.2",
        "fields": ["company_name", "registration_number", "jurisdiction", "address", "director", "owner"],
        "preferred_sources": ["ln", "registry", "official", "doc", "qcc", "web"],
        "allowed_research_sources": ["ln", "registry", "official", "doc", "qcc", "web"],
        "blocked_exclusion_fields": ["address", "company_name", "business_address"],
        "prohibited_shortcuts": ["地址相同即认定同一企业", "营业地址不同即自动排除"],
    },
    "address": {
        "id": "ADDRESS_CHECK_V0.2",
        "fields": ["address", "jurisdiction", "room", "registered_entities", "date"],
        "preferred_sources": ["ln", "registry", "official", "doc", "web"],
        "allowed_research_sources": ["ln", "registry", "official", "doc", "web"],
        "blocked_exclusion_fields": ["address", "region", "room", "jurisdiction"],
        "prohibited_shortcuts": ["共享办公地址即制裁命中", "地址字符串不同即不存在关联"],
    }
}

def get_skill(entity_type: str) -> dict:
    if entity_type not in SKILLS:
        raise ValueError(f"unrecognized skill entity_type: {entity_type}")
    return SKILLS[entity_type]

def ordered_queries(skill: dict, keys: list[str]) -> list[str]:
    priority = skill["preferred_sources"]
    return sorted(keys, key=lambda key: priority.index(key.split(":", 1)[0])
                  if key.split(":", 1)[0] in priority else len(priority))
