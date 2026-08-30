import os
from datetime import UTC, datetime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# 这些导入保持历史兼容，已有调用方可以继续从 app.main 获取相关符号。
from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIDispositionInput, AIRun, AIRunInput, AIModelConfig
from app.ai_service import (
    ModelRequest, MockModelService, OpenAICompatibleModelService, UnavailableModelService,
    validate_output, validate_requirement_analysis_output,
)
from app.asset_repository import AssetRepository
from app.asset_schemas import AssetContentInput, AssetProvenanceInput, AssetProvenanceRecord, HashVerification
from app.case_api import register_case_routes
from app.case_repository import CaseGenerationRepository
from app.case_review_api import register_case_review_routes
from app.case_review_repository import CaseReviewRepository
from app.change_impact_api import register_change_impact_routes
from app.change_impact_repository import ChangeImpactRepository
from app.design_api import register_design_routes
from app.design_repository import DesignRepository
from app.evaluation_api import register_evaluation_routes
from app.evaluation_repository import EvaluationRepository
from app.execution_batch_api import register_execution_batch_routes
from app.execution_batch_repository import ExecutionBatchRepository
from app.execution_result_api import register_execution_result_routes
from app.execution_result_repository import ExecutionResultRepository
from app.main_route_context import AppRouteContext as _AppRouteContext
from app.model_config_api import get_session_model_config, register_model_config_routes
from app.project_asset_api import register_project_asset_routes as _register_project_asset_routes
from app.project_asset_api import require_asset, require_project
from app.quality_api import register_quality_routes
from app.quality_repository import QualityRepository
from app.report_api import register_report_routes
from app.report_service import ReportService
from app.requirement_api import register_requirement_routes as _register_requirement_routes
from app.requirement_repository import RequirementRepository
from app.requirement_review_api import register_requirement_review_routes as _register_requirement_review_routes
from app.requirement_review_api import require_review
from app.requirement_service import build_requirement_package
from app.requirement_schemas import RequirementPackage, RequirementPackageInput, RequirementVersion
from app.repository import ProjectRepository
from app.review_repository import RequirementReviewRepository
from app.review_schemas import (
    AtomicRequirementUpdate, FindingUpdate, RequirementAnalysis, RequirementAnalysisInput,
    RequirementConfirmationInput, RequirementConflict, RequirementConflictDecisionInput,
    RequirementReviewFinding, RequirementSelectionInput, VisualInferenceUpdate,
)
from app.review_service import build_analysis_candidates, semantic_output_to_analysis, source_reference_exists
from app.schemas import Project, ProjectInput
from app.task_api import register_task_routes
from app.task_repository import TestTaskRepository
from app.template_api import register_template_routes
from app.template_repository import TemplateMappingRepository
from app.ai_run_api import register_ai_run_routes as _register_ai_run_routes


def create_app(database_path: Path | None = None) -> FastAPI:
    """创建应用并按历史顺序组装所有依赖和路由。"""
    resolved_database_path = database_path or Path(os.getenv("APP_DATABASE_PATH", "data/app.db"))
    repository = ProjectRepository(resolved_database_path)
    asset_repository = AssetRepository(resolved_database_path)
    requirement_repository = RequirementRepository(resolved_database_path)
    review_repository = RequirementReviewRepository(resolved_database_path)
    design_repository = DesignRepository(resolved_database_path)
    ai_run_repository = AIRunRepository(resolved_database_path)
    template_repository = TemplateMappingRepository(resolved_database_path)
    case_generation_repository = CaseGenerationRepository(resolved_database_path)
    case_review_repository = CaseReviewRepository(resolved_database_path)
    task_repository = TestTaskRepository(resolved_database_path)
    execution_batch_repository = ExecutionBatchRepository(resolved_database_path)
    execution_result_repository = ExecutionResultRepository(resolved_database_path)
    quality_repository = QualityRepository(resolved_database_path)
    change_impact_repository = ChangeImpactRepository(resolved_database_path)
    evaluation_repository = EvaluationRepository(resolved_database_path)
    report_service = ReportService(
        asset_repository, requirement_repository, review_repository, design_repository,
        template_repository, case_generation_repository, case_review_repository, task_repository,
        execution_batch_repository, execution_result_repository, quality_repository,
        change_impact_repository, ai_run_repository, evaluation_repository,
    )
    model_service = MockModelService()
    real_model_service = OpenAICompatibleModelService()
    unavailable_model_service = UnavailableModelService()
    context = _AppRouteContext(
        repository, asset_repository, requirement_repository, review_repository, design_repository,
        ai_run_repository, template_repository, case_generation_repository, case_review_repository,
        task_repository, execution_batch_repository, execution_result_repository, quality_repository,
        change_impact_repository, evaluation_repository, report_service, model_service,
        real_model_service, unavailable_model_service,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        repository.migrate()
        yield

    app = FastAPI(title="AI 测试设计与治理平台", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_design_routes(
        app, repository, requirement_repository, review_repository, design_repository, ai_run_repository
    )
    register_template_routes(app, repository, template_repository)
    register_case_routes(
        app, repository, requirement_repository, review_repository, design_repository, template_repository,
        case_generation_repository, ai_run_repository, model_service, real_model_service,
    )
    register_case_review_routes(
        app, repository, case_generation_repository, case_review_repository, ai_run_repository,
        requirement_repository, template_repository, model_service, real_model_service,
    )
    register_task_routes(app, repository, case_review_repository, task_repository)
    register_execution_batch_routes(
        app, repository, task_repository, case_review_repository, case_generation_repository,
        design_repository, execution_batch_repository,
    )
    register_execution_result_routes(app, repository, execution_batch_repository, execution_result_repository)
    register_quality_routes(
        app, repository, requirement_repository, review_repository, design_repository, case_review_repository,
        case_generation_repository, execution_batch_repository, execution_result_repository, quality_repository,
        ai_run_repository,
    )
    register_change_impact_routes(
        app, repository, requirement_repository, review_repository, design_repository, case_review_repository,
        execution_batch_repository, execution_result_repository, quality_repository, task_repository,
        ai_run_repository, change_impact_repository,
    )
    register_report_routes(app, repository, report_service)
    register_evaluation_routes(
        app, repository, asset_repository, ai_run_repository, evaluation_repository
    )
    register_model_config_routes(app)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    _register_project_asset_routes(app, context)
    _register_requirement_routes(app, context)
    _register_requirement_review_routes(app, context)
    register_design_routes(
        app, repository, requirement_repository, review_repository, design_repository, ai_run_repository
    )
    _register_ai_run_routes(app, context)
    return app


app = create_app()
