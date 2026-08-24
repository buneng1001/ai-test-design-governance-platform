from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.requirement_schemas import SourceReference


ReviewFindingType = Literal[
    "ambiguity",
    "omission",
    "conflict",
    "untestable",
    "missing_acceptance_criteria",
    "dependency_unclear",
    "missing_constraint_or_error_handling",
    "visual_inference_pending",
    "other",
]
ReviewFindingStatus = Literal[
    "pending_confirmation",
    "accepted",
    "rejected",
    "awaiting_external_confirmation",
    "resolved",
    "risk_accepted",
]
CandidateDecision = Literal["pending_confirmation", "accepted", "rejected"]
VisualDecision = Literal["pending_confirmation", "accepted", "rejected"]


class AtomicRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    stable_requirement_id: str | None = None
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    source_reference: SourceReference
    decision: CandidateDecision = "pending_confirmation"
    created_at: datetime
    updated_at: datetime


class RequirementReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    finding_type: ReviewFindingType
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    source_reference: SourceReference | None = None
    inference_marker: str | None = None
    status: ReviewFindingStatus = "pending_confirmation"
    created_at: datetime
    updated_at: datetime


class VisualInference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inference_id: str
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    source_reference: SourceReference
    decision: VisualDecision = "pending_confirmation"
    created_at: datetime
    updated_at: datetime


class RequirementAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    requirement_version_id: int
    status: Literal["draft", "confirmed"] = "draft"
    atomic_requirements: list[AtomicRequirement] = Field(default_factory=list)
    findings: list[RequirementReviewFinding] = Field(default_factory=list)
    visual_inferences: list[VisualInference] = Field(default_factory=list)
    ai_run_id: int | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None


class AtomicRequirementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None = None
    source_reference: SourceReference | None = None
    decision: CandidateDecision | None = None
    split_into: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    ] | None = None
    merge_candidate_ids: list[str] | None = None


class FindingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReviewFindingStatus
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)] | None = None


class VisualInferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: VisualDecision


class RequirementConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
