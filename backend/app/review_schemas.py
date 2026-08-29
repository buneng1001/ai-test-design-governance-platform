from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.requirement_schemas import SourceReference
from app.ai_schemas import MockScenario


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
RequirementType = Literal["functional", "interface", "data", "quality", "constraint", "workflow", "other"]
CandidateDecision = Literal["pending_confirmation", "accepted", "rejected"]
VisualDecision = Literal["pending_confirmation", "accepted", "rejected"]
ConflictDecision = Literal["unresolved", "srs_preferred", "implementation_preferred", "both_retained", "awaiting_external_confirmation"]


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
    source_reference: SourceReference
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


class AnalyzedRequirement(BaseModel):
    """模型归并后的需求，保留来源以便回到原始资料复核。"""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    requirement_type: RequirementType
    module: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    source_references: list[SourceReference] = Field(min_length=1, max_length=20)
    analysis_note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class RequirementConflict(BaseModel):
    """同一能力的多份资料不一致时，供人工裁决的独立冲突记录。"""

    model_config = ConfigDict(extra="forbid")

    conflict_id: str
    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    srs_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    srs_source: SourceReference
    implementation_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    implementation_source: SourceReference
    affected_modules: list[Annotated[str, StringConstraints(min_length=1, max_length=200)]] = Field(min_length=1)
    affected_test_items: list[str] = Field(default_factory=list)
    decision: ConflictDecision = "unresolved"
    decided_by: str | None = None
    decision_note: str | None = None


class AnalyzedTestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_item_id: str
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    module: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    requirement_ids: list[str] = Field(min_length=1, max_length=20)
    source_references: list[SourceReference] = Field(min_length=1, max_length=20)


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    requirement_id: str
    source_references: list[SourceReference] = Field(min_length=1, max_length=20)


class AnalysisFindingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    finding_type: ReviewFindingType
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    source_reference: SourceReference | None = None
    inference_marker: str | None = None


class StructuredAnalysisOutput(BaseModel):
    """需求分析模型的稳定输出契约；所有语义结果均需有来源引用。"""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["requirement-analysis.v1"]
    requirements: list[AnalyzedRequirement] = Field(max_length=100)
    test_items: list[AnalyzedTestItem] = Field(max_length=200)
    acceptance_criteria: list[AcceptanceCriterion] = Field(max_length=200)
    findings: list[AnalysisFindingOutput] = Field(max_length=200)
    conflicts: list[RequirementConflict] = Field(default_factory=list, max_length=100)


class RequirementAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    requirement_version_id: int
    status: Literal["draft", "confirmed"] = "draft"
    atomic_requirements: list[AtomicRequirement] = Field(default_factory=list)
    findings: list[RequirementReviewFinding] = Field(default_factory=list)
    visual_inferences: list[VisualInference] = Field(default_factory=list)
    requirements: list[AnalyzedRequirement] = Field(default_factory=list)
    conflicts: list[RequirementConflict] = Field(default_factory=list)
    selected_requirement_ids: list[str] = Field(default_factory=list)
    test_items: list[AnalyzedTestItem] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    ai_run_id: int | None = None
    is_mock: bool = True
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


class RequirementSelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_requirement_ids: list[str] = Field(max_length=100)


class RequirementConflictDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ConflictDecision
    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    decision_note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] | None = None


class RequirementAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["mock", "real"] = "mock"
    scenario: MockScenario = "normal"
    max_retries: int = Field(default=2, ge=0, le=2)
