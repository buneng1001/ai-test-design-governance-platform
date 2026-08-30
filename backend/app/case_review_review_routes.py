from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, status

from app.ai_schemas import AIAttempt, AIModelConfig, AIRun
from app.ai_service import ModelRequest, validate_output
from app.case_review_routes_context import CaseReviewRouteDependencies
from app.case_review_schemas import (
    CaseConfirmationInput, CaseReviewBatch, CaseReviewBatchInput, SuggestionDispositionInput,
    CaseRevision,
)
from app.case_review_service import ROLES, build_review_batch, create_revision
from app.design_service import stable_id
from app.model_config_api import get_session_model_config


def register_review_routes(router: APIRouter, deps: CaseReviewRouteDependencies) -> None:
    @router.post(
        "/api/projects/{project_id}/case-generations/{generation_id}/reviews",
        response_model=CaseReviewBatch, status_code=status.HTTP_201_CREATED,
    )
    def create_reviews(
        project_id: int, generation_id: int, data: CaseReviewBatchInput,
        x_session_id: str | None = Header(default=None),
    ) -> CaseReviewBatch:
        _require_project(deps, project_id)
        generation = deps.generations.get(project_id, generation_id)
        if generation is None or not generation.candidates:
            raise HTTPException(status_code=409, detail="存在候选测试用例后才能发起评审")
        version = deps.requirements.get_version(project_id, generation.requirement_version_id)
        if version is None:
            raise HTTPException(status_code=409, detail="候选测试用例缺少需求版本上下文")
        existing = deps.reviews.latest_for_generation(project_id, generation_id)
        if existing is not None:
            return existing
        created_runs: dict[str, int] = {}
        session_config = get_session_model_config(x_session_id) if data.mode == "real" else None
        if data.mode == "real" and session_config is None:
            raise HTTPException(status_code=422, detail="未配置真实模型；请先保存当前会话模型配置")
        asset_versions = tuple(
            {"asset_id": material.asset_id, "revision": material.asset_revision}
            for material in version.materials
        )
        for role in ROLES:
            model_parameters = AIModelConfig(
                provider=session_config.provider if session_config else "mock",
                model=session_config.model if session_config else "deterministic-v1",
            )
            request = ModelRequest(
                task_type="case_review", prompt_version=f"case-review.v1.{role}",
                model_parameters=model_parameters, input_asset_versions=asset_versions, scenario=data.scenario,
                base_url=session_config.base_url if session_config else "",
                api_key=session_config.api_key if session_config else "",
            )
            service = deps.real_model_service if data.mode == "real" else deps.mock_service
            response = service.complete(request)
            output, errors = validate_output(getattr(response, "raw_output", None))
            run_status = (
                "succeeded" if not errors and not response.error_code
                else "validation_failed" if errors else "failed"
            )
            run = deps.ai_runs.create_run(AIRun(
                id=0, project_id=project_id, task_type="case_review", model_parameters=model_parameters,
                prompt_version=f"case-review.v1.{role}", input_asset_versions=list(asset_versions), output=output,
                validation_status="passed" if run_status == "succeeded" else "failed",
                validation_errors=errors or ([response.error_code] if response.error_code else []), status=run_status,
                is_mock=data.mode == "mock", created_at=datetime.now(UTC), attempts=[AIAttempt(
                    attempt=1, started_at=datetime.now(UTC), elapsed_ms=0,
                    status="succeeded" if run_status == "succeeded" else "validation_failed" if errors else "failed",
                    error_code=response.error_code, retryable=response.retryable,
                )],
            ))
            if run_status != "succeeded":
                raise HTTPException(
                    status_code=422 if errors else 503,
                    detail={"code": "review_ai_failed", "ai_run_id": run.id},
                )
            created_runs[role] = run.id
        batch = build_review_batch(0, project_id, generation_id, generation.candidates, created_runs)
        return deps.reviews.create(batch)

    @router.get("/api/projects/{project_id}/case-review-batches/{batch_id}", response_model=CaseReviewBatch)
    def get_review(project_id: int, batch_id: int) -> CaseReviewBatch:
        _require_project(deps, project_id)
        batch = deps.reviews.get(project_id, batch_id)
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
        _require_project(deps, project_id)
        batch = deps.reviews.get(project_id, batch_id)
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
        generation = deps.generations.get(project_id, batch.generation_id)
        assert generation is not None
        candidate_revision = max(
            (item for item in batch.revisions if item.candidate_id == suggestion.candidate_id),
            key=lambda item: item.revision, default=None,
        )
        candidate = candidate_revision.candidate if candidate_revision else next(
            item for item in generation.candidates if item.id == suggestion.candidate_id
        )
        suggestion.disposition, suggestion.disposition_reason = data.decision, data.reason
        suggestion.modified_fields = data.modified_fields
        create_revision(batch, suggestion, candidate)
        if candidate_revision and candidate_revision.original_candidate:
            batch.revisions[-1].original_candidate = candidate_revision.original_candidate
        return deps.reviews.save(batch, "suggestion_disposed")

    @router.post(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/confirm",
        response_model=CaseReviewBatch,
    )
    def confirm_cases(project_id: int, batch_id: int, data: CaseConfirmationInput) -> CaseReviewBatch:
        _require_project(deps, project_id)
        batch = deps.reviews.get(project_id, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="评审批次不存在")
        if any(item.disposition is None for item in batch.suggestions):
            raise HTTPException(status_code=409, detail="所有 AI 评审建议处置后才能完成用例确认")
        candidate_ids = {item.candidate_id for item in batch.suggestions}
        if set(data.inclusion) != candidate_ids:
            raise HTTPException(status_code=422, detail="必须为每个候选测试用例提供用例纳入决定")
        generation = deps.generations.get(project_id, batch.generation_id)
        assert generation is not None
        for candidate in generation.candidates:
            stable_case_id = stable_id("case", candidate.id)
            candidate_revisions = [item for item in batch.revisions if item.candidate_id == candidate.id]
            if not candidate_revisions:
                batch.revisions.append(CaseRevision(
                    id=stable_id("case-revision", f"{batch.id}:{candidate.id}:1"), candidate_id=candidate.id,
                    revision=1, stable_case_id=stable_case_id, external_case_number=candidate.external_case_number,
                    lifecycle_status="effective",
                    participation_status="included" if data.inclusion[candidate.id] else "not_included",
                    candidate=candidate, created_at=datetime.now(UTC),
                ))
                continue
            latest_revision = max(candidate_revisions, key=lambda item: item.revision)
            for revision in candidate_revisions:
                revision.stable_case_id = stable_case_id
                revision.external_case_number = candidate.external_case_number
            batch.revisions.append(CaseRevision(
                id=stable_id("case-revision", f"{batch.id}:{candidate.id}:{latest_revision.revision + 1}"),
                candidate_id=candidate.id, revision=latest_revision.revision + 1,
                stable_case_id=stable_case_id, external_case_number=latest_revision.external_case_number,
                lifecycle_status="effective",
                participation_status="included" if data.inclusion[candidate.id] else "not_included",
                candidate=latest_revision.candidate, original_candidate=latest_revision.original_candidate,
                review_notes=["用例确认时分配稳定用例 ID"], created_at=datetime.now(UTC),
            ))
        batch.inclusion = data.inclusion
        batch.confirmed_by = data.confirmer_name
        batch.status = "confirmed"
        return deps.reviews.save(batch, "case_confirmed")

    @router.get("/api/projects/{project_id}/case-review-batches/{batch_id}/history")
    def review_history(project_id: int, batch_id: int) -> list[dict]:
        _require_project(deps, project_id)
        history = deps.reviews.history(project_id, batch_id)
        if history is None:
            raise HTTPException(status_code=404, detail="评审批次不存在")
        return history


def _require_project(deps: CaseReviewRouteDependencies, project_id: int) -> None:
    if deps.projects.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")
