from fastapi import FastAPI, HTTPException

from app.main_route_context import AppRouteContext
from app.workflow_schemas import ProjectWorkflowView
from app.workflow_service import build_project_workflow_view


def register_workflow_routes(app: FastAPI, context: AppRouteContext) -> None:
    @app.get("/api/projects/{project_id}/workflow", response_model=ProjectWorkflowView)
    def get_project_workflow(project_id: int) -> ProjectWorkflowView:
        if context.repository.get(project_id) is None:
            raise HTTPException(status_code=404, detail="测试设计项目不存在")
        return build_project_workflow_view(
            project_id,
            context.requirement_repository,
            context.review_repository,
            context.design_repository,
            context.case_generation_repository,
            context.case_review_repository,
        )
