from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


ExecutionTarget = Literal[
    "manual", "test_execution_diagnostics", "generic_automation", "external_executor", "unspecified"
]
VerdictMethod = Literal["expected_result_match", "manual_observation", "adapter_defined"]


class TestTaskCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_case_id: str
    case_revision_id: str
    case_revision: int = Field(ge=1)
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    priority: Literal["P0", "P1", "P2", "P3"]
    preconditions: list[str] = Field(min_length=1)
    parameters: dict[str, str] = Field(default_factory=dict)
    steps: list[dict[str, str | int]] = Field(min_length=1)
    expected_result: str = Field(min_length=1, max_length=1000)
    verdict_method: VerdictMethod
    evidence_requirements: list[str] = Field(min_length=1)


class TestTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["test-task.v1"] = "test-task.v1"
    task_id: str
    task_version: int = Field(ge=1)
    project_id: int
    case_review_batch_id: int
    execution_scope: Literal["selected"] = "selected"
    execution_target: ExecutionTarget
    cases: list[TestTaskCase] = Field(min_length=1)
    published_by: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    published_at: datetime


class TaskPublicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    execution_target: ExecutionTarget
    stable_case_ids: list[str] = Field(min_length=1)
    target_extension: dict[str, str] = Field(default_factory=dict)


class AdapterConversionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: TestTask
    target_extension: dict[str, str] = Field(default_factory=dict)


class TargetTaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["test-execution-diagnostics-task.v1"] = (
        "test-execution-diagnostics-task.v1"
    )
    adapter: Literal["test_execution_diagnostics"] = "test_execution_diagnostics"
    task_id: str
    task_version: int = Field(ge=1)
    cases: list[TestTaskCase] = Field(min_length=1)
    target_extension: dict[str, str] = Field(default_factory=dict)


class TargetResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["test-execution-diagnostics-result.v1"] = (
        "test-execution-diagnostics-result.v1"
    )
    task_id: str
    task_version: int = Field(ge=1)
    stable_case_id: str
    case_revision_id: str
    verdict: Literal["passed", "failed", "blocked", "not_executed", "execution_error"]
    evidence_references: list[str] = Field(default_factory=list)


class RunResultFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["run-result-feedback.v1"] = "run-result-feedback.v1"
    task_id: str
    task_version: int = Field(ge=1)
    stable_case_id: str
    case_revision_id: str
    verdict: Literal["passed", "failed", "blocked", "not_executed", "execution_error"]
    evidence_references: list[str] = Field(default_factory=list)
