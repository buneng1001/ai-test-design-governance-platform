from fastapi import FastAPI, HTTPException, status

from app.ai_repository import AIRunRepository
from app.asset_repository import AssetRepository
from app.evaluation_repository import EvaluationRepository
from app.evaluation_schemas import EvaluationRun, EvaluationRunInput
from app.evaluation_service import create_evaluation
from app.repository import ProjectRepository


def register_evaluation_routes(
    app: FastAPI,
    repository: ProjectRepository,
    assets: AssetRepository,
    ai_runs: AIRunRepository,
    evaluations: EvaluationRepository,
) -> None:
    @app.post(
        "/api/projects/{project_id}/ai-evaluations",
        response_model=EvaluationRun,
        status_code=status.HTTP_201_CREATED,
    )
    def run_evaluation(project_id: int, data: EvaluationRunInput) -> EvaluationRun:
        _require_project(repository, project_id)
        try:
            return create_evaluation(project_id, data, assets, ai_runs, evaluations)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    @app.get("/api/projects/{project_id}/ai-evaluations", response_model=list[EvaluationRun])
    def list_evaluations(project_id: int) -> list[EvaluationRun]:
        _require_project(repository, project_id)
        return evaluations.list(project_id)


def _require_project(repository: ProjectRepository, project_id: int) -> None:
    if repository.get(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试设计项目不存在")
