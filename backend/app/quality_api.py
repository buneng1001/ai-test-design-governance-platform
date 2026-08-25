from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, status

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIModelConfig, AIRun
from app.case_review_repository import CaseReviewRepository
from app.case_repository import CaseGenerationRepository
from app.coverage_service import build_coverage
from app.design_repository import DesignRepository
from app.execution_batch_repository import ExecutionBatchRepository
from app.execution_result_repository import ExecutionResultRepository
from app.quality_repository import QualityRepository
from app.quality_schemas import (
    DefectPatternCandidate,
    DefectPatternConfirmationInput,
    DefectPatternSuggestionInput,
    QualityIssueInput,
    QualityIssueReference,
)
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.review_repository import RequirementReviewRepository


def register_quality_routes(
    app: FastAPI,
    projects: ProjectRepository,
    requirements: RequirementRepository,
    reviews: RequirementReviewRepository,
    designs: DesignRepository,
    case_reviews: CaseReviewRepository,
    generations: CaseGenerationRepository,
    batches: ExecutionBatchRepository,
    results: ExecutionResultRepository,
    quality: QualityRepository,
    ai_runs: AIRunRepository,
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/quality-issues", response_model=QualityIssueReference,
        status_code=status.HTTP_201_CREATED,
    )
    def create_quality_issue(project_id: int, data: QualityIssueInput) -> QualityIssueReference:
        _require_project(projects, project_id)
        execution_result = results.get(project_id, data.execution_result_id)
        if execution_result is None:
            raise HTTPException(status_code=422, detail="质量问题引用的执行记录不存在")
        if data.retest_result_id is not None:
            retest_result = results.get(project_id, data.retest_result_id)
            if (
                retest_result is None
                or retest_result.batch_id != execution_result.batch_id
                or retest_result.retest_of_result_id != data.execution_result_id
            ):
                raise HTTPException(status_code=422, detail="质量问题引用的复测记录必须属于同一执行批次")
        return quality.create_issue(project_id, data, execution_result.batch_id, execution_result.stable_case_id)

    @router.get("/api/projects/{project_id}/quality-issues", response_model=list[QualityIssueReference])
    def list_quality_issues(project_id: int) -> list[QualityIssueReference]:
        _require_project(projects, project_id)
        return quality.list_issues(project_id)

    @router.post(
        "/api/projects/{project_id}/defect-patterns/suggestions", response_model=DefectPatternCandidate,
        status_code=status.HTTP_201_CREATED,
    )
    def suggest_pattern(project_id: int, data: DefectPatternSuggestionInput) -> DefectPatternCandidate:
        _require_project(projects, project_id)
        issues = {item.id: item for item in quality.list_issues(project_id)}
        selected = [issues.get(issue_id) for issue_id in data.quality_issue_ids]
        if len(selected) != len(data.quality_issue_ids) or any(item is None for item in selected):
            raise HTTPException(status_code=422, detail="缺陷模式只能引用当前项目的质量问题引用")
        assert all(item is not None for item in selected)
        ai_run = ai_runs.create_run(AIRun(
            id=0, project_id=project_id, task_type="defect_pattern_suggestion",
            model_parameters=AIModelConfig(), prompt_version="defect-pattern.v1", input_asset_versions=[],
            output={"contract_version": "ai-output.v1", "quality_issue_ids": data.quality_issue_ids},
            validation_status="passed", validation_errors=[], status="succeeded", is_mock=True,
            created_at=datetime.now(UTC), attempts=[
                AIAttempt(attempt=1, started_at=datetime.now(UTC), elapsed_ms=0, status="succeeded")
            ],
        ))
        # 候选模式先进入人工确认关口，且明确不把重复现象扩展成技术根因。
        pattern = DefectPatternCandidate(
            id=0, project_id=project_id,
            name="；".join(item.problem_pattern for item in selected if item)[:200],
            repeated_phenomenon="；".join(item.phenomenon for item in selected if item),
            trigger_features=sorted({item.problem_pattern for item in selected if item}),
            quality_issue_ids=data.quality_issue_ids,
            created_at=ai_run.created_at,
        )
        return quality.create_pattern(pattern)

    @router.post(
        "/api/projects/{project_id}/defect-patterns/{pattern_id}/confirm",
        response_model=DefectPatternCandidate,
    )
    def confirm_pattern(
        project_id: int, pattern_id: int, data: DefectPatternConfirmationInput
    ) -> DefectPatternCandidate:
        _require_project(projects, project_id)
        pattern = quality.get_pattern(project_id, pattern_id)
        if pattern is None:
            raise HTTPException(status_code=404, detail="缺陷模式不存在")
        if pattern.status != "pending_confirmation":
            raise HTTPException(status_code=409, detail="缺陷模式已经完成处置")
        pattern.status, pattern.confirmed_by, pattern.confirmed_at = "confirmed", data.confirmer_name, datetime.now(UTC)
        return quality.save_pattern(pattern)

    @router.get("/api/projects/{project_id}/coverage")
    def get_coverage(project_id: int, requirement_version_id: int, design_id: int,
                     case_review_batch_id: int, execution_batch_id: int | None = None) -> dict:
        _require_project(projects, project_id)
        review = reviews.latest_for_version(project_id, requirement_version_id)
        design = designs.get(project_id, design_id)
        case_review = case_reviews.get(project_id, case_review_batch_id)
        generation = generations.get(project_id, case_review.generation_id) if case_review else None
        batch = batches.get(project_id, execution_batch_id) if execution_batch_id else None
        if execution_batch_id is not None and batch is None:
            raise HTTPException(status_code=404, detail="执行批次不存在")
        execution_results = results.list_records(execution_batch_id) if execution_batch_id else []
        if (
            requirements.get_version(project_id, requirement_version_id) is None
            or design is None
            or case_review is None
            or generation is None
            or generation.design_id != design_id
            or generation.requirement_version_id != requirement_version_id
            or case_review.status != "confirmed"
            or design.status != "confirmed"
        ):
            raise HTTPException(status_code=404, detail="覆盖指标所需的确认资产不存在")
        open_conflict_result_ids = {
            result_id for conflict in results.list_conflicts(execution_batch_id or 0)
            if conflict.status == "open" for result_id in conflict.result_ids
        }
        return build_coverage(review, design, case_review, batch, execution_results,
                              [item.model_dump(mode="json") for item in quality.list_issues(project_id)],
                              open_conflict_result_ids)

    app.include_router(router)


def _require_project(projects: ProjectRepository, project_id: int) -> None:
    if projects.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")
