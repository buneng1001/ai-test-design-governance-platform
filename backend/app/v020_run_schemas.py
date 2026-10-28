from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.v020_contracts import MAX_SKILL_ANALYSIS_ROWS, TEST_TYPES


RunMode = Literal["direct", "skill", "local"]
RunPage = Literal["understanding", "analysis", "suggestions", "review", "cases"]
ReviewRole = Literal["product_manager", "project_manager", "test_manager"]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


def _recognized_test_type(value: str) -> str:
    if value not in TEST_TYPES:
        raise ValueError("测试类型必须使用平台认可的常见测试分类")
    return value


TestType = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    AfterValidator(_recognized_test_type),
]


class RunPreflightInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: RunPage
    mode: RunMode
    roles: list[ReviewRole] = Field(default_factory=list, max_length=3)
    template_mode: Literal["default", "uploaded"] = "default"
    template_mapping_id: int | None = Field(default=None, gt=0)
    supplemental_requirements: Annotated[str, Field(max_length=4000)] = ""


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: RunMode
    confirmed: bool = False
    run_id: Annotated[str, StringConstraints(pattern=r"^run-[a-zA-Z0-9-]{8,80}$")] | None = None


class ReviewRunInput(RunInput):
    roles: list[ReviewRole] = Field(min_length=1, max_length=3)


class CaseRunInput(RunInput):
    template_mode: Literal["default", "uploaded"]
    template_mapping_id: int | None = Field(default=None, gt=0)
    supplemental_requirements: Annotated[str, Field(max_length=4000)] = ""


class SelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_ids: list[str] = Field(min_length=1, max_length=1000)
    selected: bool


class DispositionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disposition: Literal["accepted", "rejected"]


class CaseEditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)] | None = None
    priority: Literal["P0", "P1", "P2", "P3"] | None = None
    preconditions: list[str] | None = None
    test_input: str | None = None
    steps: list[dict] | None = None
    overall_expectation: str | None = None


class InclusionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    included: bool


class RemovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    removed: bool


class TemplateSelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["default", "uploaded"]
    mapping_id: int | None = Field(default=None, gt=0)


class AnalysisOutputRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module: NonEmptyText
    test_item: NonEmptyText
    test_basis: NonEmptyText
    source_reference_id: NonEmptyText
    test_type: TestType
    priority: Literal["P0", "P1", "P2", "P3"]
    related_requirement_id: NonEmptyText

class AnalysisModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[AnalysisOutputRow] = Field(min_length=1, max_length=MAX_SKILL_ANALYSIS_ROWS)


class MaterialUnderstandingFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_reference_id: NonEmptyText
    title: NonEmptyText
    summary: NonEmptyText
    key_points: list[NonEmptyText] = Field(min_length=1, max_length=30)
    constraints: list[NonEmptyText] = Field(default_factory=list, max_length=30)
    ambiguities: list[NonEmptyText] = Field(default_factory=list, max_length=30)


class MaterialUnderstandingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overview: NonEmptyText
    organized_fragments: list[MaterialUnderstandingFragment] = Field(min_length=1, max_length=200)


class SuggestionOutputItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggestion_action: Literal["add", "remove", "risk"] = "add"
    module: NonEmptyText
    test_item: NonEmptyText
    test_basis: NonEmptyText
    test_type: TestType
    priority: Literal["P0", "P1", "P2", "P3"]
    related_requirement_id: NonEmptyText
    related_analysis_row_id: str | None = None

class SuggestionModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggestions: list[SuggestionOutputItem] = Field(min_length=1, max_length=100)


class ReviewOutputItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: ReviewRole
    suggestion_action: Literal["add", "remove", "risk"]
    module: NonEmptyText
    test_item: NonEmptyText
    test_basis: NonEmptyText
    test_type: TestType
    priority: Literal["P0", "P1", "P2", "P3"]
    related_requirement_id: NonEmptyText
    related_analysis_row_id: str | None = None

class ReviewRoleReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: ReviewRole
    summary: NonEmptyText
    strengths: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    concerns: list[NonEmptyText] = Field(default_factory=list, max_length=20)


class ReviewModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reports: list[ReviewRoleReport] = Field(min_length=1, max_length=3)
    suggestions: list[ReviewOutputItem] = Field(min_length=1, max_length=100)


class CaseOutputItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_row_id: NonEmptyText
    title: NonEmptyText
    objective: NonEmptyText
    preconditions: list[NonEmptyText] = Field(min_length=1, max_length=20)
    test_input: NonEmptyText
    steps: list[dict] = Field(min_length=1, max_length=50)
    overall_expectation: NonEmptyText
    evidence_requirements: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    design_basis: list[NonEmptyText] = Field(min_length=1, max_length=10)
    priority: Literal["P0", "P1", "P2", "P3"]
    attachment: str = ""


class CaseModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[CaseOutputItem] = Field(min_length=1, max_length=500)
