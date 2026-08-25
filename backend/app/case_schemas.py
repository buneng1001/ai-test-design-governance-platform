from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

from app.requirement_schemas import SourceReference


CaseVariant = Literal["normal", "boundary", "equivalence", "invalid", "scenario"]
CaseLifecycleStatus = Literal["draft", "effective", "closed", "deprecated", "superseded"]
CaseParticipationStatus = Literal["included", "not_included", "pending_impact", "pending_retest"]


class TestStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    action: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    input: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    expected: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class CaseDesignBasis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["boundary", "equivalence", "state_transition", "risk_based", "scenario"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    source_references: list[SourceReference] = Field(min_length=1)


class CandidateTestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: int
    generation_id: int
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    external_case_number: str | None = None
    objective: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    variant: CaseVariant
    preconditions: list[str] = Field(min_length=1)
    steps: list[TestStep] = Field(min_length=1)
    overall_expectation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    evidence_requirements: list[str] = Field(min_length=1)
    requirement_ids: list[str] = Field(min_length=1)
    requirement_references: list[SourceReference] = Field(min_length=1)
    scope_item_id: str
    risk_item_id: str
    priority: Literal["P0", "P1", "P2", "P3"]
    case_sheet_name: str
    automation_mapping: str | None = None
    unexpressed_fields: list[str] = Field(default_factory=list)
    design_basis: list[CaseDesignBasis] = Field(min_length=1)
    created_at: datetime


class CaseGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_mapping_id: int = Field(gt=0)
    scenario: Literal[
        "normal", "empty", "missing_source", "invalid_schema", "timeout", "rate_limit", "temporary_error",
        "authentication_error", "parameter_error", "content_safety_error"
    ] = "normal"
    max_retries: int = Field(default=2, ge=0, le=2)
    variants: list[CaseVariant] = Field(
        default_factory=lambda: ["normal", "boundary", "invalid"], min_length=1, max_length=5
    )
    accept_template_limitations: bool = False


class CaseGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    design_id: int
    requirement_version_id: int
    template_mapping_id: int
    ai_run_id: int
    ai_run_status: str
    is_mock: bool
    candidates: list[CandidateTestCase] = Field(default_factory=list)
    template_diagnostics: list[dict] = Field(default_factory=list)
    status: Literal["succeeded", "empty", "validation_failed", "failed", "needs_confirmation"]
    created_at: datetime
