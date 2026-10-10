from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


RunMode = Literal["direct", "skill", "local"]
RunPage = Literal["analysis", "suggestions", "review", "cases"]
ReviewRole = Literal["product_manager", "project_manager", "test_manager"]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


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
    function_point: NonEmptyText
    test_item: NonEmptyText
    test_point: NonEmptyText
    source_reference_id: NonEmptyText
    ai_reason: NonEmptyText
    information_gap: str = ""
    status: Literal["ready", "needs_information"] = "ready"


class AnalysisModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[AnalysisOutputRow] = Field(min_length=1, max_length=500)


class SuggestionOutputItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggestion_type: Literal["function", "test_item", "test_point"]
    priority: Literal["high", "medium", "low"]
    content: NonEmptyText
    related_analysis_row_id: str | None = None
    ai_reason: NonEmptyText


class SuggestionModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggestions: list[SuggestionOutputItem] = Field(min_length=1, max_length=100)


class ReviewOutputItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: ReviewRole
    finding_type: Literal["risk", "omission", "conflict", "change"]
    content: NonEmptyText
    related_analysis_row_id: str | None = None
    ai_reason: NonEmptyText


class ReviewModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    evidence_requirements: list[NonEmptyText] = Field(min_length=1, max_length=20)
    design_basis: list[NonEmptyText] = Field(min_length=1, max_length=10)
    priority: Literal["P0", "P1", "P2", "P3"]


class CaseModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[CaseOutputItem] = Field(min_length=1, max_length=500)
