"""Policy boundary: business authorities must approve any operational disposition."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Policy:
    version: str = "CANDIDATE-0.2"
    max_research_actions_per_hit: int = 3
    # Proposed rule candidates can be disabled individually without patching Python logic.
    disabled_rules: frozenset[str] = field(default_factory=frozenset)
    # Only local, explicitly permitted adapters are callable in this release.
    allowed_tool_names: frozenset[str] = field(default_factory=lambda: frozenset({"fixture_research", "document_intelligence"}))
    # Company-approved categories are deliberately EMPTY by default.
    mandatory_compliance_categories: frozenset[str] = field(default_factory=frozenset)
    approved_exclusion_rules: frozenset[str] = field(default_factory=frozenset)
    # This is a preliminary screening-review flag, not compulsory escalation to compliance.
    unresolved_mandatory_review: frozenset[str] = field(default_factory=lambda: frozenset({"sanctions"}))
    allow_automatic_ln_disposition: bool = False
    # Optional additional evidence threshold for reviewed DOCUMENT-EXTRACTED facts.
    # Defaults to False for backward-compatible V0.4 review; V0.5 demonstration
    # sets True. This is a proposed control, not an LN/company requirement.
    require_independent_corroboration_for_document_facts: bool = False
    minimum_independent_sources: int = 2
    # No whitelist or auto-not-report switches exist: those actions are not implemented.
    # Phase-II prototype only. Do not use to make a production regulatory decision.
    suspicion_weights: tuple[tuple[str, int], ...] = (
        ("name_exact", 1), ("region_overlap", 2), ("address_overlap", 3), ("company_link", 3),
        ("dob_exact", 3), ("ongoing_pep", 2), ("former_pep", -1),
        ("recent_adverse_event", 2), ("sanctions_category", 4))
    suspicion_report_threshold: int = 7
    suspicion_review_threshold: int = 3
