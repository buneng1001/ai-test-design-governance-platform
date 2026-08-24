from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

from app.requirement_schemas import SourceReference


DesignStatus = Literal["draft", "confirmed"]
DimensionStatus = Literal["active", "inactive"]
AutomationDecision = Literal[
    "priority_automation",
    "suitable_automation",
    "conditional_automation",
    "manual_execution",
]


class TestDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    parent_id: str | None = None
    status: DimensionStatus = "active"
    sort_order: int = 0


class TestScopeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    requirement_ids: list[str] = Field(min_length=1)
    primary_dimension_id: str
    secondary_dimension_ids: list[str] = Field(default_factory=list)
    business_criticality: int = Field(default=3, ge=1, le=5)
    requirement_change_level: int = Field(default=0, ge=0, le=5)
    historical_failure_count: int = Field(default=0, ge=0, le=5)


class RiskFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    score: int = Field(ge=1, le=5)
    weight: int = Field(default=1, ge=1, le=10)
    suggested_score: int | None = Field(default=None, ge=1, le=5)
    suggestion_reason: str | None = None
    source_references: list[SourceReference] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_item_id: str
    factors: list[RiskFactor] = Field(min_length=1)
    final_score: int = Field(ge=1, le=100)
    risk_level: Literal["high", "medium", "low"]
    priority: Literal["P0", "P1", "P2", "P3"]
    adjustment_reason: str | None = None


class AutomationFactors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regression_value: int = Field(ge=1, le=5)
    determinism: int = Field(ge=1, le=5)
    environment_control: int = Field(ge=1, le=5)
    saving_benefit: int = Field(ge=1, le=5)
    maintenance_cost: int = Field(ge=1, le=5)
    manual_observation: int = Field(ge=1, le=5)


class AutomationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_item_id: str
    factors: AutomationFactors
    suggested_score: int = Field(ge=0, le=100)
    suggestion_reason: str
    decision: AutomationDecision = "manual_execution"
    decision_reason: str | None = None


class DesignAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    requirement_version_id: int
    status: DesignStatus = "draft"
    dimensions: list[TestDimension] = Field(default_factory=list)
    scope_items: list[TestScopeItem] = Field(default_factory=list)
    risks: list[RiskAssessment] = Field(default_factory=list)
    automation_candidates: list[AutomationCandidate] = Field(default_factory=list)
    ai_run_id: int | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None


class DesignCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension_names: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    ] = Field(
        default_factory=lambda: ["功能", "接口", "数据", "异常恢复"]
    )


class DimensionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    parent_id: str | None = None
    sort_order: int = 0


class DimensionUpdate(DimensionInput):
    status: DimensionStatus = "active"


class DimensionMergeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_dimension_id: str


class ScopeItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    requirement_ids: list[str] = Field(min_length=1)
    primary_dimension_id: str
    secondary_dimension_ids: list[str] = Field(default_factory=list)
    business_criticality: int = Field(default=3, ge=1, le=5)
    requirement_change_level: int = Field(default=0, ge=0, le=5)
    historical_failure_count: int = Field(default=0, ge=0, le=5)


class RiskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factors: list[RiskFactor] = Field(min_length=1)
    adjustment_reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ] | None = None


class AutomationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factors: AutomationFactors
    decision: AutomationDecision
    decision_reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ] | None = None


class DesignConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
