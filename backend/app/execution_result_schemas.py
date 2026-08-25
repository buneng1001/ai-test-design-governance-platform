from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


ResultStatus = Literal["passed", "execution_failed", "blocked", "not_executed", "execution_error"]
SourceType = Literal["manual", "test_execution_diagnostics", "generic_automation"]


class ExecutionResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_record_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    stable_case_id: str | None = None
    case_revision_id: str | None = None
    external_case_number: str | None = None
    execution_record_id: str | None = None
    status: ResultStatus
    actual_result: str = ""
    reason: str = ""
    executor: str = ""
    executed_at: datetime | None = None
    evidence_references: list[str] = Field(default_factory=list)
    retest_of_result_id: int | None = Field(default=None, ge=1)


class ExecutionResultImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    results: list[ExecutionResultInput] = Field(min_length=1)


class ExecutionResultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    batch_id: int
    source_type: SourceType
    source_record_id: str
    stable_case_id: str | None = None
    case_revision_id: str | None = None
    external_case_number: str | None = None
    execution_record_id: str | None = None
    execution_sequence: int | None = None
    status: ResultStatus
    actual_result: str
    reason: str
    executor: str
    executed_at: datetime | None = None
    evidence_references: list[str]
    match_status: Literal["matched", "unresolved", "rejected"]
    match_reason: str | None = None
    matched_by: str | None = None
    retest_of_result_id: int | None = None
    created_at: datetime


class ResultMatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["matched", "rejected"]
    stable_case_id: str | None = None
    case_revision_id: str | None = None
    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ResultConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    batch_id: int
    result_ids: list[int]
    statuses: dict[str, ResultStatus]
    status: Literal["open", "resolved"]
    decision: ResultStatus | None = None
    rationale: str | None = None
    confirmed_by: str | None = None


class ResultConflictResolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ResultStatus
    rationale: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class BatchConclusionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion: ResultStatus
    rationale: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CaseResultSummary(BaseModel):
    stable_case_id: str
    initial_result: ExecutionResultRecord | None = None
    latest_result: ExecutionResultRecord | None = None
    history: list[ExecutionResultRecord]


class ExecutionBatchResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int
    records: list[ExecutionResultRecord]
    unresolved_records: list[ExecutionResultRecord]
    conflicts: list[ResultConflict]
    case_summaries: list[CaseResultSummary]
    conclusion: BatchConclusionInput | None = None
