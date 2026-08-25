from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


QualityIssueSeverity = Literal["low", "medium", "high", "critical"]
QualityIssueStatus = Literal["open", "in_progress", "resolved", "accepted_risk"]
ReleaseImpact = Literal["none", "monitor", "blocks_release"]
PatternStatus = Literal["pending_confirmation", "confirmed", "rejected"]


class QualityIssueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_result_id: int = Field(ge=1)
    phenomenon: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    evidence_references: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    ] = Field(min_length=1)
    severity: QualityIssueSeverity
    problem_pattern: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    external_defect_number: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    status: QualityIssueStatus = "open"
    release_impact: ReleaseImpact = "none"
    fix_version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    retest_result_id: int | None = Field(default=None, ge=1)


class QualityIssueReference(QualityIssueInput):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    batch_id: int
    stable_case_id: str | None = None
    created_at: datetime


class DefectPatternCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    repeated_phenomenon: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    trigger_features: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    ] = Field(min_length=1)
    quality_issue_ids: list[int] = Field(min_length=2)
    root_cause_claim: Literal["not_established"] = "not_established"
    status: PatternStatus = "pending_confirmation"
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


class DefectPatternSuggestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quality_issue_ids: list[int] = Field(min_length=2)


class DefectPatternConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
