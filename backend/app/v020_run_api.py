from fastapi import APIRouter, FastAPI, Header, HTTPException, Response, status

from app.v020_run_repository import V020RunRepository
from app.v020_run_schemas import (
    CaseEditInput, CaseRunInput, DispositionInput, InclusionInput, RemovalInput, ReviewRunInput,
    RunInput, RunPreflightInput, SelectionInput,
)
from app.v020_model_errors import V020RunError
from app.v020_run_service import V020RunService


def register_v020_run_routes(
    app: FastAPI, service: V020RunService, repository: V020RunRepository,
) -> None:
    router = APIRouter(prefix="/api/v0.2/projects/{project_id}")

    @router.post("/run-preflight")
    def preflight(
        project_id: int, data: RunPreflightInput, x_session_id: str | None = Header(default=None),
    ) -> dict:
        return _call(
            service.preflight, project_id, data.page, data.mode, x_session_id, data.roles,
            template_mode=data.template_mode, template_mapping_id=data.template_mapping_id,
            supplemental_requirements=data.supplemental_requirements,
        )

    @router.post("/analysis-runs", status_code=status.HTTP_201_CREATED)
    def analysis_run(
        project_id: int, data: RunInput, response: Response, x_session_id: str | None = Header(default=None),
    ) -> dict:
        result = _call(service.run, project_id, "analysis", data.mode, data.confirmed, x_session_id,
                       requested_run_id=data.run_id)
        if result.get("reused"):
            response.status_code = status.HTTP_200_OK
        return result

    @router.post("/material-understanding-runs", status_code=status.HTTP_201_CREATED)
    def material_understanding_run(
        project_id: int, data: RunInput, response: Response, x_session_id: str | None = Header(default=None),
    ) -> dict:
        result = _call(service.run, project_id, "understanding", data.mode, data.confirmed, x_session_id,
                       requested_run_id=data.run_id)
        if result.get("reused"):
            response.status_code = status.HTTP_200_OK
        return result

    @router.patch("/analysis-selection")
    def update_selection(project_id: int, data: SelectionInput) -> dict:
        try:
            count = repository.set_selection(project_id, data.row_ids, data.selected)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"selected_count": count, "affected_count": len(data.row_ids)}

    @router.post("/suggestion-runs", status_code=status.HTTP_201_CREATED)
    def suggestion_run(
        project_id: int, data: RunInput, response: Response, x_session_id: str | None = Header(default=None),
    ) -> dict:
        result = _call(service.run, project_id, "suggestions", data.mode, data.confirmed, x_session_id,
                       requested_run_id=data.run_id)
        if result.get("reused"):
            response.status_code = status.HTTP_200_OK
        return result

    @router.patch("/suggestions/{suggestion_id}")
    def dispose_suggestion(project_id: int, suggestion_id: str, data: DispositionInput) -> dict:
        return _call(service.accept_item, project_id, "suggestion", suggestion_id, data.disposition)

    @router.post("/review-runs", status_code=status.HTTP_201_CREATED)
    def review_run(
        project_id: int, data: ReviewRunInput, response: Response, x_session_id: str | None = Header(default=None),
    ) -> dict:
        result = _call(
            service.run, project_id, "review", data.mode, data.confirmed, x_session_id, roles=data.roles,
            requested_run_id=data.run_id,
        )
        if result.get("reused"):
            response.status_code = status.HTTP_200_OK
        return result

    @router.patch("/review-suggestions/{suggestion_id}")
    def dispose_review_suggestion(project_id: int, suggestion_id: str, data: DispositionInput) -> dict:
        return _call(service.accept_item, project_id, "review", suggestion_id, data.disposition)

    @router.post("/review-skip")
    def skip_review(project_id: int) -> dict:
        return _call(service.skip_review, project_id)

    @router.post("/case-runs", status_code=status.HTTP_201_CREATED)
    def case_run(
        project_id: int, data: CaseRunInput, response: Response, x_session_id: str | None = Header(default=None),
    ) -> dict:
        result = _call(
            service.run, project_id, "cases", data.mode, data.confirmed, x_session_id,
            template_mode=data.template_mode, template_mapping_id=data.template_mapping_id,
            supplemental_requirements=data.supplemental_requirements,
            requested_run_id=data.run_id,
        )
        if result.get("reused"):
            response.status_code = status.HTTP_200_OK
        return result

    @router.patch("/cases/{case_id}")
    def edit_case(project_id: int, case_id: str, data: CaseEditInput) -> dict:
        return _call(service.edit_case, project_id, case_id, data.model_dump(exclude_none=True))

    @router.get("/runs/{run_id}")
    def get_run(project_id: int, run_id: str) -> dict:
        run = repository.get_run(project_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行记录不存在")
        return run

    @router.post("/runs/{run_id}/cancel")
    def cancel_run(project_id: int, run_id: str) -> dict:
        run = repository.request_cancel(project_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行记录不存在")
        return run

    @router.patch("/cases/{case_id}/inclusion")
    def set_case_inclusion(project_id: int, case_id: str, data: InclusionInput) -> dict:
        return _call(service.edit_case, project_id, case_id, {"included": data.included})

    @router.patch("/cases/{case_id}/removal")
    def set_case_removal(project_id: int, case_id: str, data: RemovalInput) -> dict:
        return _call(service.edit_case, project_id, case_id, {"removed": data.removed})

    app.include_router(router)


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except V020RunError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
