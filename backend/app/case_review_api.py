from fastapi import APIRouter, FastAPI, HTTPException

from app.ai_repository import AIRunRepository
from app.ai_service import MockModelService, OpenAICompatibleModelService
from app.case_repository import CaseGenerationRepository
from app.case_review_edit_routes import register_edit_routes
from app.case_review_export_routes import register_export_routes
from app.case_review_replacement_routes import register_replacement_routes
from app.case_review_review_routes import register_review_routes
from app.case_review_routes_context import CaseReviewRouteDependencies
from app.case_review_status_routes import register_status_routes
from app.case_review_repository import CaseReviewRepository
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.template_repository import TemplateMappingRepository


def register_case_review_routes(
    app: FastAPI, projects: ProjectRepository, generations: CaseGenerationRepository,
    reviews: CaseReviewRepository, ai_runs: AIRunRepository, requirements: RequirementRepository,
    templates: TemplateMappingRepository, mock_service: MockModelService,
    real_model_service: OpenAICompatibleModelService,
) -> None:
    """注册用例评审相关路由，并保留原有统一入口。"""
    deps = CaseReviewRouteDependencies(
        projects=projects, generations=generations, reviews=reviews, ai_runs=ai_runs,
        requirements=requirements, templates=templates, mock_service=mock_service,
        real_model_service=real_model_service,
    )
    router = APIRouter()
    register_review_routes(router, deps)
    register_edit_routes(router, deps)
    register_status_routes(router, deps)
    register_replacement_routes(router, deps)
    register_export_routes(router, deps)
    app.include_router(router)


def _require_project(repository: ProjectRepository, project_id: int) -> None:
    """保留拆分前的兼容签名，供历史导入方继续校验项目。"""
    if repository.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")


__all__ = ["register_case_review_routes", "_require_project"]
