from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

from app.case_schemas import CandidateTestCase, CaseLifecycleStatus, CaseParticipationStatus
from app.requirement_schemas import SourceReference


ReviewerRole = Literal["product_manager", "test_manager", "project_manager"]
SuggestionType = Literal["supplement", "modify", "delete", "risk"]
Disposition = Literal["accepted", "rejected", "modified"]


class ReviewSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    candidate_id: str
    role: ReviewerRole
    suggestion_type: SuggestionType
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    rationale: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    source_references: list[SourceReference] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    group_id: str | None = None
    disposition: Disposition | None = None
    disposition_reason: str | None = None
    modified_fields: dict[str, str] = Field(default_factory=dict)


class ReviewGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    candidate_id: str
    summary: str
    original_suggestion_ids: list[str] = Field(min_length=1)
    source_roles: list[ReviewerRole] = Field(min_length=1)


class CaseRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    candidate_id: str
    revision: int = Field(ge=1)
    stable_case_id: str | None = None
    external_case_number: str | None = None
    lifecycle_status: CaseLifecycleStatus = "draft"
    participation_status: CaseParticipationStatus = "not_included"
    superseded_by_case_id: str | None = None
    candidate: CandidateTestCase
    review_notes: list[str] = Field(default_factory=list)
    original_candidate: CandidateTestCase | None = None
    manual_modified: bool = False
    edit_history: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime


class CaseReviewBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: Literal[
        "normal", "empty", "missing_source", "invalid_schema", "timeout", "rate_limit", "temporary_error",
        "authentication_error", "parameter_error", "content_safety_error",
    ] = "normal"
    max_retries: int = Field(default=2, ge=0, le=2)
    mode: Literal["mock", "real"] = "mock"


class SuggestionDispositionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Disposition
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    modified_fields: dict[str, str] = Field(default_factory=dict)


class CaseConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    inclusion: dict[str, bool]


class CaseStatusChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lifecycle_status: CaseLifecycleStatus | None = None
    participation_status: CaseParticipationStatus | None = None
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CaseBatchStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_case_ids: list[str] = Field(min_length=1)
    participation_status: CaseParticipationStatus
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CaseEditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    priority: Literal["P0", "P1", "P2", "P3"] | None = None
    preconditions: list[str] | None = None
    input: str | None = None
    steps: list[dict[str, str | int]] | None = None
    overall_expectation: str | None = None
    test_type: str | None = None
    module: str | None = None
    test_item: str | None = None
    pre_test_notes: str | None = None
    software_version: str | None = None
    restore_original: bool = False
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] = "人工编辑用例"


class CaseStatusChangeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_case_id: str
    previous_lifecycle_status: CaseLifecycleStatus
    lifecycle_status: CaseLifecycleStatus
    previous_participation_status: CaseParticipationStatus
    participation_status: CaseParticipationStatus
    reason: str
    confirmer_name: str
    changed_at: datetime


class CaseReplacementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: CandidateTestCase
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CaseExportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["all", "selected", "changed"] = "all"
    stable_case_ids: list[str] = Field(default_factory=list)


class ReviewerRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ReviewerRole
    ai_run_id: int
    candidate_ids: list[str] = Field(min_length=1)
    input_context: dict


class CaseReviewBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    generation_id: int
    status: Literal["in_progress", "completed", "confirmed"]
    reviewer_runs: list[ReviewerRun] = Field(min_length=3, max_length=3)
    suggestions: list[ReviewSuggestion] = Field(default_factory=list)
    groups: list[ReviewGroup] = Field(default_factory=list)
    revisions: list[CaseRevision] = Field(default_factory=list)
    status_changes: list[CaseStatusChangeRecord] = Field(default_factory=list)
    inclusion: dict[str, bool] = Field(default_factory=dict)
    confirmed_by: str | None = None
    created_at: datetime
