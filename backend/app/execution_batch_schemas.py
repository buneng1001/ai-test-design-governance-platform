from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


class ExecutionCaseSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_case_id: str
    case_revision_id: str
    case_revision: int = Field(ge=1)
    external_case_number: str | None = None
    lifecycle_status: Literal["effective", "closed", "deprecated", "superseded"]
    participation_status: Literal["included", "not_included", "pending_impact", "pending_retest"]
    execution_sequence: int = Field(ge=1)
    display_number: str
    title: str
    priority: Literal["P0", "P1", "P2", "P3"]
    preconditions: list[str] = Field(min_length=1)
    parameters: dict[str, str] = Field(default_factory=dict)
    steps: list[dict[str, str | int]] = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    verdict_method: Literal["expected_result_match", "manual_observation", "adapter_defined"]
    evidence_requirements: list[str] = Field(min_length=1)


class ExecutionBatchCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    requirement_version_id: int = Field(ge=1)
    environment: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    scope: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    responsible_person: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    stable_case_ids: list[str] = Field(min_length=1)


class ExecutionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    test_task_id: str
    test_task_version: int = Field(ge=1)
    product_version: str
    requirement_version_id: int = Field(ge=1)
    environment: str
    scope: str
    responsible_person: str
    execution_target: str
    cases: list[ExecutionCaseSnapshot] = Field(min_length=1)
    manual_file_format: Literal["csv"] = "csv"
    created_at: datetime


class ManualExecutionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_record_id: str
    stable_case_id: str
    case_revision_id: str
    external_case_number: str | None = None
    execution_sequence: int = Field(ge=1)
    display_number: str
    title: str
    filling_status: Literal["未填写"] = "未填写"
    actual_result: str = ""
    reason: str = ""
    executor: str = ""
    executed_at: str = ""
    evidence_references: str = ""
