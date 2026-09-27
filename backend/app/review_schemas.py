from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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
SuggestionDirection = Literal["normal", "exception", "boundary", "risk"]
SuggestionSourceType = Literal["material_explicit", "human_confirmed", "analysis_inference", "awaiting_confirmation"]
SuggestionDisposition = Literal["pending_confirmation", "accepted", "rejected", "modified", "awaiting_external_confirmation"]
SupplementalRequirementDecision = Literal["pending_confirmation", "confirmed"]


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
    # 发现项可能是模型的综合判断，无法映射到单一原文时允许后续人工补充来源。
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


class ReviewSuggestion(BaseModel):
    """Step 03～06 的可处置建议；建议与需求事实保持分离。"""

    model_config = ConfigDict(extra="forbid")

    suggestion_id: str
    direction: SuggestionDirection
    problem_type: ReviewFindingType
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    source_type: SuggestionSourceType
    source_references: list[SourceReference] = Field(min_length=1, max_length=20)
    related_requirement_ids: list[str] = Field(min_length=1, max_length=20)
    impact_scope: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    proposed_requirement_statement: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ] | None = None
    disposition: SuggestionDisposition = "pending_confirmation"
    created_at: datetime
    updated_at: datetime


class SupplementalRequirementCandidate(BaseModel):
    """由已采纳建议派生，但尚未重新确认的需求候选。"""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    source_references: list[SourceReference] = Field(min_length=1, max_length=20)
    related_requirement_ids: list[str] = Field(min_length=1, max_length=20)
    decision: SupplementalRequirementDecision = "pending_confirmation"
    stable_requirement_id: str | None = None
    created_at: datetime
    updated_at: datetime
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None


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
    analysis_status: Literal["ready", "blocked"] = "ready"


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

    @model_validator(mode="after")
    def validate_unique_relationships(self) -> "StructuredAnalysisOutput":
        requirement_ids = [item.requirement_id for item in self.requirements]
        test_item_ids = [item.test_item_id for item in self.test_items]
        criterion_ids = [item.criterion_id for item in self.acceptance_criteria]
        finding_ids = [item.finding_id for item in self.findings]
        conflict_ids = [item.conflict_id for item in self.conflicts]
        collections = {
            "需求": requirement_ids,
            "测试项": test_item_ids,
            "验收条件": criterion_ids,
            "评审发现": finding_ids,
            "冲突": conflict_ids,
        }
        for label, identifiers in collections.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{label} ID 必须唯一")
        known_requirement_ids = set(requirement_ids)
        if any(not set(item.requirement_ids).issubset(known_requirement_ids) for item in self.test_items):
            raise ValueError("测试项只能关联同批有效需求")
        if any(item.requirement_id not in known_requirement_ids for item in self.acceptance_criteria):
            raise ValueError("验收条件只能关联同批有效需求")
        if any(not set(item.affected_test_items).issubset(set(test_item_ids)) for item in self.conflicts):
            raise ValueError("冲突只能关联同批有效测试项")
        return self


class AnalysisBatch(BaseModel):
    """单个受控分析批次的结果摘要，诊断细节保留在对应 AI 运行中。"""

    model_config = ConfigDict(extra="forbid")

    batch_number: int = Field(ge=1)
    source_reference_ids: list[str] = Field(min_length=1)
    status: Literal["completed"]
    ai_run_id: int


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
    suggestions: list[ReviewSuggestion] = Field(default_factory=list)
    supplemental_requirement_candidates: list[SupplementalRequirementCandidate] = Field(default_factory=list)
    analysis_batches: list[AnalysisBatch] = Field(default_factory=list)
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
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None = None
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)] | None = None


class SuggestionDispositionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: Literal["accepted", "rejected", "modified", "awaiting_external_confirmation"]
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None = None

    @model_validator(mode="after")
    def require_text_for_modified_suggestion(self) -> "SuggestionDispositionInput":
        if self.disposition == "modified" and self.statement is None:
            raise ValueError("修改建议时必须提供修改后的内容")
        return self


class SupplementalRequirementConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[str] = Field(min_length=1, max_length=100)
    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class AtomicRequirementBulkConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[str] = Field(min_length=1)


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
    batch_size: int = Field(default=25, ge=1, le=50)
    force_new: bool = False
