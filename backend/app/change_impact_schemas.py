from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

from app.requirement_schemas import SourceReference


ChangeType = Literal["added", "modified", "deleted", "split", "merged", "suspected_continuation"]
ChangeStatus = Literal["pending_confirmation", "confirmed", "rejected"]
RegressionReason = Literal[
    "requirement_change", "high_risk", "historical_failure", "result_conflict", "open_quality_issue",
    "defect_pattern", "adjacent_state", "long_not_executed", "ai_supplement",
]


class RequirementChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    change_type: ChangeType
    summary: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    base_requirement_id: str | None = None
    target_requirement_id: str | None = None
    base_source_reference: SourceReference | None = None
    target_source_reference: SourceReference | None = None
    status: ChangeStatus = "pending_confirmation"
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None


class ChangeImpactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version_id: int = Field(gt=0)
    target_version_id: int = Field(gt=0)


class ChangeConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    decisions: dict[str, ChangeStatus]


class ImpactLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["scope", "risk", "case", "task"]
    identifier: str
    title: str
    change_ids: list[str] = Field(min_length=1)
    reason: str


class RegressionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_case_id: str
    title: str
    deterministic: bool = True
    reasons: list[RegressionReason] = Field(min_length=1)
    ai_supplement_reason: str | None = None
    selected: bool | None = None
    decision_reason: str | None = None


class ChangeImpactAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    base_version_id: int
    target_version_id: int
    status: Literal["pending_change_confirmation", "confirmed"] = "pending_change_confirmation"
    changes: list[RequirementChange]
    impacts: list[ImpactLink] = Field(default_factory=list)
    regression_candidates: list[RegressionCandidate] = Field(default_factory=list)
    ai_supplements: list[RegressionCandidate] = Field(default_factory=list)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


class RegressionConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    decisions: dict[str, bool]
    reasons: dict[str, Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]] = Field(
        default_factory=dict
    )


class RegressionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    analysis_id: int
    candidates: list[RegressionCandidate]
    status: Literal["pending_confirmation", "confirmed"] = "pending_confirmation"
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime
