from fastapi import APIRouter, FastAPI, Header, HTTPException, status

from app.v020_run_repository import V020RunRepository
from app.v020_run_schemas import (
    CaseEditInput, CaseRunInput, DispositionInput, InclusionInput, RemovalInput, ReviewRunInput,
    RunInput, RunPreflightInput, SelectionInput,
)
from app.v020_run_service import V020RunError, V020RunService


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
        project_id: int, data: RunInput, x_session_id: str | None = Header(default=None),
    ) -> dict:
        return _call(service.run, project_id, "analysis", data.mode, data.confirmed, x_session_id)

    @router.patch("/analysis-selection")
    def update_selection(project_id: int, data: SelectionInput) -> dict:
        try:
            count = repository.set_selection(project_id, data.row_ids, data.selected)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"selected_count": count, "affected_count": len(data.row_ids)}

    @router.post("/suggestion-runs", status_code=status.HTTP_201_CREATED)
    def suggestion_run(
        project_id: int, data: RunInput, x_session_id: str | None = Header(default=None),
    ) -> dict:
        return _call(service.run, project_id, "suggestions", data.mode, data.confirmed, x_session_id)

    @router.patch("/suggestions/{suggestion_id}")
    def dispose_suggestion(project_id: int, suggestion_id: str, data: DispositionInput) -> dict:
        return _call(service.accept_item, project_id, "suggestion", suggestion_id, data.disposition)

    @router.post("/review-runs", status_code=status.HTTP_201_CREATED)
    def review_run(
        project_id: int, data: ReviewRunInput, x_session_id: str | None = Header(default=None),
    ) -> dict:
        return _call(
            service.run, project_id, "review", data.mode, data.confirmed, x_session_id, roles=data.roles,
        )

    @router.patch("/review-suggestions/{suggestion_id}")
    def dispose_review_suggestion(project_id: int, suggestion_id: str, data: DispositionInput) -> dict:
        return _call(service.accept_item, project_id, "review", suggestion_id, data.disposition)

    @router.post("/review-skip")
    def skip_review(project_id: int) -> dict:
        return _call(service.skip_review, project_id)

    @router.post("/case-runs", status_code=status.HTTP_201_CREATED)
    def case_run(
        project_id: int, data: CaseRunInput, x_session_id: str | None = Header(default=None),
    ) -> dict:
        return _call(
            service.run, project_id, "cases", data.mode, data.confirmed, x_session_id,
            template_mode=data.template_mode, template_mapping_id=data.template_mapping_id,
            supplemental_requirements=data.supplemental_requirements,
        )

    @router.patch("/cases/{case_id}")
    def edit_case(project_id: int, case_id: str, data: CaseEditInput) -> dict:
        return _call(service.edit_case, project_id, case_id, data.model_dump(exclude_none=True))

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
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
