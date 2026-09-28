from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
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
    candidate_key: str = ""
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
    # 模板中的执行阶段字段和项目上下文，生成阶段只填设计字段。
    test_type: str = "功能"
    input: str = ""
    module: str = ""
    test_item: str = ""
    test_result: str = ""
    test_record: str = ""
    pre_test_notes: str = ""
    planned_execution_time: str = ""
    attachment: str = ""
    software_version: str = ""
    platform_test_point_id: str | None = None
    skill_test_point_id: str | None = None
    template_fallback: bool = False
    # 模型不能把待确认内容写成需求事实；它们仅作为人工审核提示保存在候选用例中。
    pending_confirmations: list[str] = Field(default_factory=list, max_length=20)


class CaseGenerationDesignBasis(BaseModel):
    """模型输出的设计依据，来源引用由平台从已确认测试点补齐。"""

    model_config = ConfigDict(extra="forbid")

    method: Literal["boundary", "equivalence", "state_transition", "risk_based", "scenario"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class CaseGenerationOutputItem(BaseModel):
    """详细用例生成的受控模型契约，内容字段不再由平台模板替代。"""

    model_config = ConfigDict(extra="forbid")

    test_point_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    variant: CaseVariant
    case_discriminator: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    objective: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    preconditions: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]] = Field(
        min_length=1, max_length=20
    )
    steps: list[TestStep] = Field(min_length=1, max_length=50)
    overall_expectation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    evidence_requirements: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]] = Field(
        min_length=1, max_length=20
    )
    design_basis: list[CaseGenerationDesignBasis] = Field(min_length=1, max_length=10)
    pending_confirmations: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def require_continuous_steps(self) -> "CaseGenerationOutputItem":
        if [step.order for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("测试步骤编号必须从 1 开始连续递增")
        texts = [self.title, self.objective, self.overall_expectation, *self.preconditions]
        texts.extend(value for step in self.steps for value in (step.action, step.input, step.expected))
        if any(marker in text for text in texts for marker in ("待确认", "不确定", "待澄清")) and not self.pending_confirmations:
            raise ValueError("用例内容包含待确认信息时必须明确标记 pending_confirmations")
        return self


class CaseGenerationModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["case-generation.v1"]
    items: list[CaseGenerationOutputItem] = Field(max_length=100)

    @model_validator(mode="after")
    def require_unique_candidate_key(self) -> "CaseGenerationModelOutput":
        keys = [(item.test_point_id, item.variant, item.case_discriminator) for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("同一测试点、用例粒度和候选区分标识不能重复生成候选")
        return self


class CandidateDraftEditInput(BaseModel):
    """候选用例在角色评审前的人工编辑；原始模型候选由生成记录保留。"""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    priority: Literal["P0", "P1", "P2", "P3"] | None = None
    preconditions: list[str] | None = None
    input: str | None = None
    steps: list[TestStep] | None = None
    overall_expectation: str | None = None
    test_type: str | None = None
    module: str | None = None
    test_item: str | None = None
    pre_test_notes: str | None = None
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] = "人工编辑候选用例"


class CandidateRemovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    removed: bool
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class CandidateHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    action: Literal["edited", "removed", "restored"]
    reason: str
    created_at: datetime


class CaseGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_mapping_id: int | None = Field(default=None, gt=0)
    mode: Literal["mock", "real", "template"] = "mock"
    scenario: Literal[
        "normal", "empty", "missing_source", "invalid_schema", "timeout", "rate_limit", "temporary_error",
        "authentication_error", "parameter_error", "content_safety_error"
    ] = "normal"
    max_retries: int = Field(default=2, ge=0, le=2)
    batch_size: int = Field(default=25, ge=1, le=50)
    run_control_id: str | None = None
    start_only: bool = False
    advance_only: bool = False
    variants: list[CaseVariant] = Field(
        default_factory=lambda: ["normal", "boundary", "invalid", "scenario"], min_length=1, max_length=5
    )
    accept_template_limitations: bool = False
    strict_conflicts: bool = False
    modules: list[str] = Field(default_factory=list, max_length=100)


class CandidateStandardExportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[str] = Field(default_factory=list)
    format: Literal["xlsx", "csv"] = "xlsx"


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
    ai_run_ids: list[int] = Field(default_factory=list)
    source: Literal["mock", "real", "template"] = "mock"
    batch_total: int = Field(default=1, ge=1)
    completed_batches: int = Field(default=0, ge=0)
    run_control_id: str | None = None
    candidates: list[CandidateTestCase] = Field(default_factory=list)
    original_candidates: list[CandidateTestCase] = Field(default_factory=list)
    removed_candidate_ids: list[str] = Field(default_factory=list)
    candidate_history: list[CandidateHistoryRecord] = Field(default_factory=list)
    template_diagnostics: list[dict] = Field(default_factory=list)
    status: Literal["succeeded", "empty", "validation_failed", "failed", "needs_confirmation"]
    created_at: datetime
