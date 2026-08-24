from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, status

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIModelConfig, AIRun
from app.ai_service import ModelRequest, MockModelService, validate_output
from app.case_repository import CaseGenerationRepository
from app.case_review_repository import CaseReviewRepository
from app.case_review_schemas import (
    CaseConfirmationInput, CaseRevision, CaseReviewBatch, CaseReviewBatchInput, SuggestionDispositionInput,
)
from app.case_review_service import ROLES, build_review_batch, create_revision
from app.design_service import stable_id
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository


def register_case_review_routes(
    app: FastAPI, projects: ProjectRepository, generations: CaseGenerationRepository,
    reviews: CaseReviewRepository, ai_runs: AIRunRepository, requirements: RequirementRepository,
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/case-generations/{generation_id}/reviews",
        response_model=CaseReviewBatch, status_code=status.HTTP_201_CREATED,
    )
    def create_reviews(project_id: int, generation_id: int, data: CaseReviewBatchInput) -> CaseReviewBatch:
        _require_project(projects, project_id)
        generation = generations.get(project_id, generation_id)
        if generation is None or not generation.candidates:
            raise HTTPException(status_code=409, detail="存在候选测试用例后才能发起评审")
        version = requirements.get_version(project_id, generation.requirement_version_id)
        if version is None:
            raise HTTPException(status_code=409, detail="候选测试用例缺少需求版本上下文")
        existing = reviews.latest_for_generation(project_id, generation_id)
        if existing is not None:
            return existing
        created_runs: dict[str, int] = {}
        asset_versions = tuple(
            {"asset_id": material.asset_id, "revision": material.asset_revision}
            for material in version.materials
        )
        for role in ROLES:
            response = MockModelService().complete(ModelRequest(
                task_type="case_review", prompt_version=f"case-review.v1.{role}",
                model_parameters=AIModelConfig(), input_asset_versions=asset_versions, scenario=data.scenario,
            ))
            output, errors = validate_output(getattr(response, "raw_output", None))
            run_status = (
                "succeeded" if not errors and not response.error_code
                else "validation_failed" if errors else "failed"
            )
            run = ai_runs.create_run(AIRun(
                id=0, project_id=project_id, task_type="case_review", model_parameters=AIModelConfig(),
                prompt_version=f"case-review.v1.{role}", input_asset_versions=list(asset_versions), output=output,
                validation_status="passed" if run_status == "succeeded" else "failed",
                validation_errors=errors or ([response.error_code] if response.error_code else []), status=run_status,
                is_mock=True, created_at=datetime.now(UTC), attempts=[AIAttempt(
                    attempt=1, started_at=datetime.now(UTC), elapsed_ms=0,
                    status="succeeded" if run_status == "succeeded" else "validation_failed" if errors else "failed",
                    error_code=response.error_code,
                    retryable=response.retryable,
                )],
            ))
            if run_status != "succeeded":
                raise HTTPException(
                    status_code=422 if errors else 503,
                    detail={"code": "review_ai_failed", "ai_run_id": run.id},
                )
            created_runs[role] = run.id
        batch = build_review_batch(0, project_id, generation_id, generation.candidates, created_runs)
        return reviews.create(batch)

    @router.get("/api/projects/{project_id}/case-review-batches/{batch_id}", response_model=CaseReviewBatch)
    def get_review(project_id: int, batch_id: int) -> CaseReviewBatch:
        _require_project(projects, project_id)
        batch = reviews.get(project_id, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="评审批次不存在")
        return batch

    @router.patch(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/suggestions/{suggestion_id}",
        response_model=CaseReviewBatch,
    )
    def dispose_suggestion(
        project_id: int, batch_id: int, suggestion_id: str, data: SuggestionDispositionInput,
    ) -> CaseReviewBatch:
        _require_project(projects, project_id)
        batch = reviews.get(project_id, batch_id)
        if batch is None or batch.status == "confirmed":
            raise HTTPException(status_code=409, detail="评审批次不存在或已经确认")
        suggestion = next((item for item in batch.suggestions if item.id == suggestion_id), None)
        if suggestion is None:
            raise HTTPException(status_code=404, detail="AI 评审建议不存在")
        if suggestion.disposition is not None:
            raise HTTPException(status_code=409, detail="AI 评审建议已经处置")
        if data.decision == "modified" and not data.modified_fields:
            raise HTTPException(status_code=422, detail="修改建议必须提供修改后的字段")
        allowed_fields = {"title", "objective", "overall_expectation"}
        if set(data.modified_fields) - allowed_fields:
            raise HTTPException(status_code=422, detail="修改建议只能调整用例公开文本字段")
        generation = generations.get(project_id, batch.generation_id)
        assert generation is not None
        candidate = next(item for item in generation.candidates if item.id == suggestion.candidate_id)
        suggestion.disposition, suggestion.disposition_reason = data.decision, data.reason
        suggestion.modified_fields = data.modified_fields
        create_revision(batch, suggestion, candidate)
        return reviews.save(batch, "suggestion_disposed")

    @router.post(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/confirm",
        response_model=CaseReviewBatch,
    )
    def confirm_cases(project_id: int, batch_id: int, data: CaseConfirmationInput) -> CaseReviewBatch:
        _require_project(projects, project_id)
        batch = reviews.get(project_id, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="评审批次不存在")
        if any(item.disposition is None for item in batch.suggestions):
            raise HTTPException(status_code=409, detail="所有 AI 评审建议处置后才能完成用例确认")
        candidate_ids = {item.candidate_id for item in batch.suggestions}
        if set(data.inclusion) != candidate_ids:
            raise HTTPException(status_code=422, detail="必须为每个候选测试用例提供用例纳入决定")
        generation = generations.get(project_id, batch.generation_id)
        assert generation is not None
        for candidate in generation.candidates:
            if not data.inclusion.get(candidate.id):
                continue
            stable_case_id = stable_id("case", candidate.id)
            candidate_revisions = [item for item in batch.revisions if item.candidate_id == candidate.id]
            if not candidate_revisions:
                batch.revisions.append(CaseRevision(
                    id=stable_id("case-revision", f"{batch.id}:{candidate.id}:1"), candidate_id=candidate.id,
                    revision=1, stable_case_id=stable_case_id, candidate=candidate,
                    created_at=datetime.now(UTC),
                ))
                continue
            latest_revision = max(candidate_revisions, key=lambda item: item.revision)
            batch.revisions.append(CaseRevision(
                id=stable_id("case-revision", f"{batch.id}:{candidate.id}:{latest_revision.revision + 1}"),
                candidate_id=candidate.id, revision=latest_revision.revision + 1,
                stable_case_id=stable_case_id, candidate=latest_revision.candidate,
                review_notes=["用例确认时分配稳定用例 ID"], created_at=datetime.now(UTC),
            ))
        batch.inclusion = data.inclusion
        batch.confirmed_by = data.confirmer_name
        batch.status = "confirmed"
        return reviews.save(batch, "case_confirmed")

    @router.get("/api/projects/{project_id}/case-review-batches/{batch_id}/history")
    def review_history(project_id: int, batch_id: int) -> list[dict]:
        _require_project(projects, project_id)
        history = reviews.history(project_id, batch_id)
        if history is None:
            raise HTTPException(status_code=404, detail="评审批次不存在")
        return history

    app.include_router(router)


def _require_project(repository: ProjectRepository, project_id: int) -> None:
    if repository.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")
