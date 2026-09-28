from datetime import UTC, datetime
from time import sleep

from fastapi import FastAPI, HTTPException

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIDispositionInput, AIRun, AIRunInput
from app.ai_run_reliability import error_category, redact_diagnostic, retry_delay_ms
from app.ai_service import ModelRequest, local_structural_repair, validate_output
from app.main_route_context import AppRouteContext
from app.project_asset_api import require_project


def register_ai_run_routes(app: FastAPI, context: AppRouteContext) -> None:
    """注册 AI 运行和审计接口。"""
    repository = context.repository
    asset_repository = context.asset_repository
    ai_run_repository: AIRunRepository = context.ai_run_repository
    controls = context.ai_run_control_repository

    @app.post("/api/projects/{project_id}/ai-workflow-runs/{run_id}/stop")
    def stop_ai_workflow_run(project_id: int, run_id: str) -> dict:
        run = controls.require(run_id)
        if run.project_id != project_id:
            raise HTTPException(status_code=404, detail="AI 运行不存在")
        return controls.request_stop(run_id).__dict__

    @app.get("/api/projects/{project_id}/ai-workflow-runs/{run_id}")
    def get_ai_workflow_run(project_id: int, run_id: str) -> dict:
        run = controls.require(run_id)
        if run.project_id != project_id:
            raise HTTPException(status_code=404, detail="AI 运行不存在")
        return run.__dict__

    @app.post("/api/projects/{project_id}/ai-runs", response_model=AIRun, status_code=201)
    def create_ai_run(project_id: int, run_input: AIRunInput) -> AIRun:
        require_project(repository.get(project_id))
        input_asset_versions = []
        for asset_id in run_input.input_asset_ids:
            asset = asset_repository.get(project_id, asset_id)
            if asset is None:
                raise HTTPException(status_code=404, detail="AI 运行输入资产不存在")
            if not asset.can_enter_model_context:
                raise HTTPException(status_code=422, detail="来源不明资产或评估真值不能进入模型上下文")
            input_asset_versions.append({"asset_id": asset.id, "revision": asset.revision})
        attempts = []
        final_output = None
        validation_errors: list[str] = []
        run_status = "failed"
        validation_status = "not_run"
        max_attempts = run_input.max_retries + 1
        request = ModelRequest(
            task_type=run_input.task_type,
            prompt_version=run_input.prompt_version,
            model_parameters=run_input.model_parameters,
            input_asset_versions=tuple(input_asset_versions),
            scenario=run_input.scenario,
        )
        selected_model_service = (
            context.model_service
            if run_input.model_parameters.provider == "mock"
            else context.unavailable_model_service
        )
        for attempt_number in range(1, max_attempts + 1):
            started_at = datetime.now(UTC)
            response = selected_model_service.complete(request)
            elapsed_ms = max(0, int((datetime.now(UTC) - started_at).total_seconds() * 1000))
            if response.error_code:
                attempts.append({
                    "attempt": attempt_number, "started_at": started_at, "elapsed_ms": elapsed_ms,
                    "status": "failed", "error_code": response.error_code, "retryable": response.retryable,
                    "diagnostic": redact_diagnostic(response.diagnostic),
                    "error_category": error_category(response.error_code),
                    "retry_after_ms": retry_delay_ms(attempt_number) if response.retryable else None,
                    "recovery_point": f"model_call.retry-{attempt_number + 1}" if response.retryable else None,
                })
                if not response.retryable or attempt_number == max_attempts:
                    break
                sleep(retry_delay_ms(attempt_number) / 1000)
                continue
            final_output, validation_errors = validate_output(response.raw_output)
            if validation_errors:
                final_output, validation_errors = validate_output(local_structural_repair(response.raw_output))
                if final_output is not None:
                    validation_status = "passed"
                    run_status = "succeeded"
                    attempts.append({
                        "attempt": attempt_number, "started_at": started_at, "elapsed_ms": elapsed_ms,
                        "status": "succeeded", "error_code": "schema_local_repaired", "retryable": False,
                        "error_category": "structure", "recovery_point": "local_structural_repair",
                    })
                    break
            if validation_errors:
                attempts.append({
                    "attempt": attempt_number, "started_at": started_at, "elapsed_ms": elapsed_ms,
                    "status": "validation_failed", "error_code": "schema_invalid", "retryable": False,
                    "error_category": "structure", "recovery_point": "structural_repair_required",
                })
                validation_status = "failed"
                run_status = "validation_failed"
                break
            validation_status = "passed"
            run_status = "succeeded"
            attempts.append({
                "attempt": attempt_number, "started_at": started_at, "elapsed_ms": elapsed_ms,
                "status": "succeeded", "error_code": None, "retryable": False,
            })
            break
        run = AIRun(
            id=0, project_id=project_id, task_type=run_input.task_type,
            model_parameters=run_input.model_parameters, prompt_version=run_input.prompt_version,
            input_asset_versions=input_asset_versions, output=final_output,
            validation_status=validation_status, validation_errors=validation_errors,
            status=run_status, is_mock=run_input.model_parameters.provider == "mock",
            created_at=datetime.now(UTC), attempts=attempts,
            source="mock" if run_input.model_parameters.provider == "mock" else "real",
            stage="model_call", total_count=len(input_asset_versions),
        )
        return ai_run_repository.create_run(run)

    @app.get("/api/projects/{project_id}/ai-runs", response_model=list[AIRun])
    def list_ai_runs(project_id: int) -> list[AIRun]:
        require_project(repository.get(project_id))
        return ai_run_repository.list(project_id)

    @app.get("/api/projects/{project_id}/ai-runs/audit-export")
    def export_ai_audit(project_id: int) -> dict:
        require_project(repository.get(project_id))
        return {
            "contract_version": "ai-audit.v1",
            "project_id": project_id,
            "runs": [run.model_dump(mode="json") for run in ai_run_repository.list(project_id)],
        }

    @app.get("/api/projects/{project_id}/ai-runs/{run_id}", response_model=AIRun)
    def get_ai_run(project_id: int, run_id: int) -> AIRun:
        require_project(repository.get(project_id))
        run = ai_run_repository.get(project_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="AI 运行不存在")
        return run

    @app.post("/api/projects/{project_id}/ai-runs/{run_id}/dispositions", response_model=AIRun)
    def create_ai_disposition(project_id: int, run_id: int, disposition: AIDispositionInput) -> AIRun:
        require_project(repository.get(project_id))
        run = ai_run_repository.add_disposition(project_id, run_id, disposition)
        if run is None:
            raise HTTPException(status_code=404, detail="AI 运行不存在")
        return run
