"""受控批次执行需求分析，并把每一批的诊断持久化为 AI 运行。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIRun, AIModelConfig, MockScenario
from app.ai_service import ModelRequest, ModelService, validate_requirement_analysis_output
from app.model_config_service import provider_error_type, service_error
from app.review_schemas import StructuredAnalysisOutput


@dataclass(frozen=True)
class CompletedAnalysisBatch:
    batch_number: int
    source_reference_ids: list[str]
    output: StructuredAnalysisOutput
    ai_run_id: int


class RequirementAnalysisBatchError(Exception):
    def __init__(self, status_code: int, detail: dict[str, object]) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def run_requirement_analysis_batches(
    *,
    project_id: int,
    model_service: ModelService,
    model_parameters: AIModelConfig,
    input_asset_versions: list[dict[str, int]],
    input_context: tuple[dict[str, object], ...],
    mode: str,
    scenario: MockScenario,
    max_retries: int,
    batch_size: int,
    ai_runs: AIRunRepository,
    base_url: str = "",
    api_key: str = "",
) -> list[CompletedAnalysisBatch]:
    batches = [input_context[index:index + batch_size] for index in range(0, len(input_context), batch_size)]
    if not batches:
        raise RequirementAnalysisBatchError(422, {"message": "需求资料中没有可分析的来源片段"})
    completed: list[CompletedAnalysisBatch] = []
    for batch_number, batch_context in enumerate(batches, start=1):
        request = ModelRequest(
            task_type="requirement_review",
            prompt_version="requirement-analysis.v1",
            model_parameters=model_parameters,
            input_asset_versions=tuple(input_asset_versions),
            scenario=scenario,
            input_context=batch_context,
            base_url=base_url,
            api_key=api_key,
        )
        output, attempts, validation_errors, run_status, diagnostic, error_code = _complete_batch(
            model_service, request, max_retries,
        )
        ai_run = ai_runs.create_run(AIRun(
            id=0,
            project_id=project_id,
            task_type="requirement_review",
            model_parameters=model_parameters,
            prompt_version="requirement-analysis.v1",
            input_asset_versions=input_asset_versions,
            output=output.model_dump(mode="json") if output else {},
            validation_status="passed" if output else "failed" if run_status == "validation_failed" else "not_run",
            validation_errors=validation_errors,
            status=run_status,
            is_mock=mode == "mock",
            created_at=datetime.now(UTC),
            attempts=attempts,
        ))
        if output is None:
            error_type = "invalid_response" if run_status == "validation_failed" else provider_error_type(error_code)
            detail = service_error(
                "model_call", model_parameters.provider, model_parameters.model, error_type,
                "schema_invalid" if run_status == "validation_failed" else diagnostic,
            ).model_dump(mode="json")
            detail["batch_number"] = batch_number
            detail["ai_run_id"] = ai_run.id
            raise RequirementAnalysisBatchError(422 if run_status == "validation_failed" else 502, detail)
        completed.append(CompletedAnalysisBatch(
            batch_number=batch_number,
            source_reference_ids=[
                str(item["source_reference"]["reference_id"])
                for item in batch_context if isinstance(item.get("source_reference"), dict)
            ],
            output=output,
            ai_run_id=ai_run.id,
        ))
    return completed


def _complete_batch(
    service: ModelService, request: ModelRequest, max_retries: int,
) -> tuple[StructuredAnalysisOutput | None, list[AIAttempt], list[str], str, str | None, str | None]:
    attempts: list[AIAttempt] = []
    validation_errors: list[str] = []
    diagnostic: str | None = None
    error_code: str | None = None
    for attempt_number in range(1, max_retries + 2):
        started_at = datetime.now(UTC)
        try:
            response = service.complete(request)
        except Exception as exc:
            attempts.append(AIAttempt(
                attempt=attempt_number, started_at=started_at, elapsed_ms=0, status="failed",
                error_code="provider_unexpected_error", retryable=False, diagnostic=type(exc).__name__,
            ))
            return None, attempts, validation_errors, "failed", type(exc).__name__, "provider_unexpected_error"
        elapsed_ms = max(0, int((datetime.now(UTC) - started_at).total_seconds() * 1000))
        if response.error_code:
            error_code, diagnostic = response.error_code, response.diagnostic
            attempts.append(AIAttempt(
                attempt=attempt_number, started_at=started_at, elapsed_ms=elapsed_ms, status="failed",
                error_code=error_code, retryable=response.retryable, diagnostic=diagnostic,
            ))
            if response.retryable and attempt_number <= max_retries:
                continue
            return None, attempts, validation_errors, "failed", diagnostic, error_code
        output, validation_errors = validate_requirement_analysis_output(response.raw_output, request.input_context)
        if validation_errors:
            attempts.append(AIAttempt(
                attempt=attempt_number, started_at=started_at, elapsed_ms=elapsed_ms,
                status="validation_failed", error_code="schema_invalid", retryable=False,
            ))
            return None, attempts, validation_errors, "validation_failed", None, "schema_invalid"
        attempts.append(AIAttempt(
            attempt=attempt_number, started_at=started_at, elapsed_ms=elapsed_ms,
            status="succeeded", error_code=None, retryable=False,
        ))
        return output, attempts, validation_errors, "succeeded", None, None
    raise RuntimeError("需求分析批次没有返回终态")


def record_aggregate_validation_failure(
    *,
    ai_runs: AIRunRepository,
    project_id: int,
    model_parameters: AIModelConfig,
    input_asset_versions: list[dict[str, int]],
    mode: str,
    diagnostic: str,
) -> int:
    """跨批校验失败也留下不可覆盖的失败运行，避免批内成功被误读为整体成功。"""
    created_at = datetime.now(UTC)
    run = ai_runs.create_run(AIRun(
        id=0,
        project_id=project_id,
        task_type="requirement_review",
        model_parameters=model_parameters,
        prompt_version="requirement-analysis.v1",
        input_asset_versions=input_asset_versions,
        output={},
        validation_status="failed",
        validation_errors=[diagnostic],
        status="validation_failed",
        is_mock=mode == "mock",
        created_at=created_at,
        attempts=[AIAttempt(
            attempt=1, started_at=created_at, elapsed_ms=0, status="validation_failed",
            error_code="aggregate_validation_failed", retryable=False,
        )],
    ))
    return run.id
