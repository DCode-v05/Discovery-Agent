"""Level 2 schemas — use-case mapping & integration gap analysis.

LLM-facing models (`LLM*`) carry the model's mapping/gap findings; domain models
(`GapReport` etc.) carry the prioritized, dependency-resolved result. Priority and
business-impact scoring are computed deterministically in `prioritizer.py` rather
than asked of the model, so the ranking is explainable and reproducible.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class GapStatus(str, Enum):
    available = "available"   # integration already exists between the two systems
    missing = "missing"       # integration must be built


class EffortLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Priority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


# --------------------------------------------------------------------------- #
# Input: automation use cases (data/use_cases.json)                           #
# --------------------------------------------------------------------------- #
class UseCaseInput(BaseModel):
    id: str
    name: str
    description: str
    frequency_per_year: int = Field(default=12, description="How often the workflow runs per year (drives business impact).")
    criticality: str = Field(default="medium", description="Business criticality: critical|high|medium|low.")


# --------------------------------------------------------------------------- #
# LLM-facing analysis output                                                  #
# --------------------------------------------------------------------------- #
class LLMDataFlow(BaseModel):
    source_system: str
    destination_system: str
    entity: str = Field(description="The data entity that moves, e.g. 'Invoice', 'Opportunity'.")
    trigger: str = Field(description="What triggers the flow, e.g. 'Opportunity marked Closed-Won'.")


class LLMUseCaseMapping(BaseModel):
    use_case_id: str
    required_systems: list[str] = Field(default_factory=list)
    data_flows: list[LLMDataFlow] = Field(default_factory=list)
    rationale: str = ""


class LLMGap(BaseModel):
    source_system: str
    destination_system: str
    integration_name: str = Field(description="Short name, e.g. 'Salesforce -> NetSuite'.")
    description: str
    status: GapStatus
    effort_level: EffortLevel
    effort_days: int = Field(ge=0, description="Rough order-of-magnitude engineering days.")
    effort_rationale: str = ""
    required_by_use_case_ids: list[str] = Field(default_factory=list)


class LLMGapAnalysis(BaseModel):
    mappings: list[LLMUseCaseMapping] = Field(default_factory=list)
    gaps: list[LLMGap] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Domain output                                                               #
# --------------------------------------------------------------------------- #
class DataFlow(BaseModel):
    source_system: str
    destination_system: str
    entity: str
    trigger: str


class UseCaseMapping(BaseModel):
    use_case_id: str
    name: str
    required_systems: list[str] = Field(default_factory=list)
    missing_systems: list[str] = Field(default_factory=list, description="Required systems absent from the inventory.")
    data_flows: list[DataFlow] = Field(default_factory=list)
    rationale: str = ""


class IntegrationGap(BaseModel):
    id: str
    source_system: str
    destination_system: str
    integration_name: str
    description: str
    status: GapStatus
    effort_level: EffortLevel
    effort_days: int
    effort_rationale: str = ""
    required_by_use_cases: list[str] = Field(default_factory=list)
    blocks_use_cases: list[str] = Field(default_factory=list, description="Use cases that cannot be automated until this gap is closed.")
    business_impact_score: float = Field(default=0.0, description="Computed: frequency x criticality x #downstream blocked.")
    priority: Priority = Priority.medium
    dependency_note: str = ""


class GapReport(BaseModel):
    run_id: str
    generated_at: str
    use_case_count: int
    gap_count: int
    mappings: list[UseCaseMapping] = Field(default_factory=list)
    gaps: list[IntegrationGap] = Field(default_factory=list)
    dependency_statements: list[str] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)
