from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


AITaskType = Literal[
    "requirement_review", "scope_analysis", "risk_analysis", "automation_assessment", "case_generation",
    "case_review", "defect_pattern_suggestion",
]
MockScenario = Literal[
    "normal",
    "empty",
    "missing_source",
    "invalid_schema",
    "timeout",
    "rate_limit",
    "temporary_error",
    "authentication_error",
    "parameter_error",
    "content_safety_error",
]
RunStatus = Literal["succeeded", "validation_failed", "failed"]
ValidationStatus = Literal["passed", "failed", "not_run"]
Disposition = Literal["accepted", "rejected", "modified"]


class AIModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] = "mock"
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] = "deterministic-v1"
    temperature: float = Field(default=0, ge=0, le=2)
    max_tokens: int = Field(default=1200, ge=1, le=10000)


class AIRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: AITaskType
    prompt_version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    input_asset_ids: list[int] = Field(default_factory=list, max_length=20)
    model_parameters: AIModelConfig = Field(default_factory=AIModelConfig)
    scenario: MockScenario = "normal"
    max_retries: int = Field(default=2, ge=0, le=2)


class AIOutputItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    source_asset_ids: list[int] = Field(min_length=1, max_length=20)


class AIOutputEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["ai-output.v1"]
    items: list[AIOutputItem] = Field(max_length=100)


class AIAttempt(BaseModel):
    attempt: int
    started_at: datetime
    elapsed_ms: int = Field(ge=0)
    status: Literal["succeeded", "validation_failed", "failed"]
    error_code: str | None = None
    retryable: bool = False


class AIRun(BaseModel):
    id: int
    project_id: int
    task_type: AITaskType
    model_parameters: AIModelConfig
    prompt_version: str
    input_asset_versions: list[dict[str, int]]
    output: dict | None
    validation_status: ValidationStatus
    validation_errors: list[str]
    status: RunStatus
    is_mock: bool
    created_at: datetime
    attempts: list[AIAttempt]
    dispositions: list[dict] = Field(default_factory=list)
    disposition: dict | None = None


class AIDispositionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Disposition
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
