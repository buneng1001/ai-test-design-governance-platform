from fastapi import FastAPI, HTTPException, Response

from app.main_route_context import AppRouteContext
from app.requirement_review_api import require_review
from app.review_schemas import RequirementAnalysis
from app.test_point_review_schemas import (
    TestPointReviewConfirmationInput,
    TestPointScopeSelectionInput,
)
from app.test_point_review_service import (
    build_test_point_review,
    confirm_review,
    export_markdown_package,
    save_selection,
)


def register_test_point_review_routes(app: FastAPI, context: AppRouteContext) -> None:
    """注册 Step 07～08 审核路由；交接快照随需求评审历史一并保留。"""
    reviews = context.review_repository

    @app.post(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review",
        response_model=RequirementAnalysis,
    )
    def generate_test_point_review(project_id: int, analysis_id: int) -> RequirementAnalysis:
        analysis = require_review(context.repository, reviews, project_id, analysis_id)
        if analysis.status != "confirmed":
            raise HTTPException(status_code=409, detail="需求确认后才能生成测试点审核")
        if not analysis.suggestions:
            raise HTTPException(status_code=409, detail="请先生成 Step 03～06 新增建议")
        if analysis.test_point_review is None:
            analysis.test_point_review = build_test_point_review(analysis)
            return reviews.save(analysis, "test_point_review_generated")
        return analysis

    @app.get(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review",
        response_model=RequirementAnalysis,
    )
    def get_test_point_review(project_id: int, analysis_id: int) -> RequirementAnalysis:
        analysis = require_review(context.repository, reviews, project_id, analysis_id)
        if analysis.test_point_review is None:
            raise HTTPException(status_code=404, detail="测试点审核尚未生成")
        return analysis

    @app.patch(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review/selection",
        response_model=RequirementAnalysis,
    )
    def update_test_point_scope(
        project_id: int, analysis_id: int, data: TestPointScopeSelectionInput
    ) -> RequirementAnalysis:
        analysis = require_review(context.repository, reviews, project_id, analysis_id)
        if analysis.test_point_review is None:
            raise HTTPException(status_code=409, detail="请先生成测试点审核")
        try:
            save_selection(analysis.test_point_review, data.test_item_ids, data.test_point_ids)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return reviews.save(analysis, "test_point_scope_selected")

    @app.post(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review/confirm",
        response_model=RequirementAnalysis,
    )
    def confirm_test_point_review(
        project_id: int, analysis_id: int, data: TestPointReviewConfirmationInput
    ) -> RequirementAnalysis:
        analysis = require_review(context.repository, reviews, project_id, analysis_id)
        if analysis.test_point_review is None:
            raise HTTPException(status_code=409, detail="请先生成测试点审核")
        try:
            confirm_review(analysis.test_point_review, data.confirmer_name)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return reviews.save(analysis, "test_point_review_confirmed")

    @app.get(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/step-00-08-package.md",
        response_class=Response,
    )
    def export_step_package(project_id: int, analysis_id: int) -> Response:
        analysis = require_review(context.repository, reviews, project_id, analysis_id)
        try:
            content = export_markdown_package(analysis)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="step-00-08-analysis-{analysis_id}.md"'},
        )
