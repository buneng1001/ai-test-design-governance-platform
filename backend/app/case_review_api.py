from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.responses import Response

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIModelConfig, AIRun
from app.ai_service import ModelRequest, MockModelService, validate_output
from app.case_repository import CaseGenerationRepository
from app.case_review_repository import CaseReviewRepository
from app.case_review_schemas import (
    CaseBatchStatusInput, CaseConfirmationInput, CaseEditInput, CaseExportInput, CaseReplacementInput,
    CaseRevision, CaseReviewBatch, CaseReviewBatchInput, CaseStatusChangeInput, CaseStatusChangeRecord,
    SuggestionDispositionInput,
)
from app.case_review_service import ROLES, build_review_batch, create_revision
from app.case_lifecycle_service import can_change_lifecycle, export_template, latest_revisions
from app.design_service import stable_id
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.template_repository import TemplateMappingRepository


def register_case_review_routes(
    app: FastAPI, projects: ProjectRepository, generations: CaseGenerationRepository,
    reviews: CaseReviewRepository, ai_runs: AIRunRepository, requirements: RequirementRepository,
    templates: TemplateMappingRepository,
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
        candidate_revision = max(
            (item for item in batch.revisions if item.candidate_id == suggestion.candidate_id),
            key=lambda item: item.revision,
            default=None,
        )
        candidate = candidate_revision.candidate if candidate_revision else next(
            item for item in generation.candidates if item.id == suggestion.candidate_id
        )
        suggestion.disposition, suggestion.disposition_reason = data.decision, data.reason
        suggestion.modified_fields = data.modified_fields
        create_revision(batch, suggestion, candidate)
        if candidate_revision and candidate_revision.original_candidate:
            batch.revisions[-1].original_candidate = candidate_revision.original_candidate
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
            stable_case_id = stable_id("case", candidate.id)
            candidate_revisions = [item for item in batch.revisions if item.candidate_id == candidate.id]
            if not candidate_revisions:
                batch.revisions.append(CaseRevision(
                    id=stable_id("case-revision", f"{batch.id}:{candidate.id}:1"), candidate_id=candidate.id,
                    revision=1, stable_case_id=stable_case_id, external_case_number=candidate.external_case_number,
                    lifecycle_status="effective",
                    participation_status="included" if data.inclusion[candidate.id] else "not_included",
                    candidate=candidate,
                    created_at=datetime.now(UTC),
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
                candidate=latest_revision.candidate,
                original_candidate=latest_revision.original_candidate,
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

    @router.patch(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/cases/{case_id}",
        response_model=CaseReviewBatch,
    )
    def edit_case(project_id: int, batch_id: int, case_id: str, data: CaseEditInput) -> CaseReviewBatch:
        """保存人工修订，并保留原始 AI 候选。"""
        _require_project(projects, project_id)
        batch = reviews.get(project_id, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="评审批次不存在")
        generation = generations.get(project_id, batch.generation_id)
        if generation is None:
            raise HTTPException(status_code=404, detail="候选测试用例生成记录不存在")
        # 编辑确认前的草稿修订还没有稳定用例 ID，恢复时也必须能找到它。
        previous = max(
            (
                item for item in batch.revisions
                if item.stable_case_id == case_id or item.candidate_id == case_id
            ),
            key=lambda item: item.revision,
            default=None,
        )
        source = previous.candidate if previous else next(
            (item for item in generation.candidates if item.id == case_id), None,
        )
        if source is None:
            raise HTTPException(status_code=404, detail="用例不存在")
        if data.restore_original:
            if previous is None or previous.original_candidate is None:
                raise HTTPException(status_code=409, detail="用例没有可恢复的原始 AI 结果")
            source = previous.original_candidate
            updates = {}
        else:
            updates = data.model_dump(exclude_none=True, exclude={"reason", "restore_original"})
        original_candidate = previous.original_candidate if previous else source
        if previous and original_candidate is None:
            original_candidate = next(
                (item for item in generation.candidates if item.id == source.id), source
            )
        if "input" in updates and "steps" not in updates:
            updates["steps"] = [step.model_copy(update={"input": updates["input"]}) for step in source.steps]
        edited = source.__class__.model_validate({**source.model_dump(), **updates})
        next_revision = (previous.revision + 1) if previous else 1
        batch.revisions.append(CaseRevision(
            id=stable_id("case-revision", f"{batch.id}:{source.id}:{next_revision}"), candidate_id=source.id,
            revision=next_revision, stable_case_id=previous.stable_case_id if previous else None,
            external_case_number=source.external_case_number,
            lifecycle_status=previous.lifecycle_status if previous else "draft",
            participation_status=previous.participation_status if previous else "not_included",
            candidate=edited, original_candidate=original_candidate,
            manual_modified=True, edit_history=(previous.edit_history if previous else []) + [{
                "reason": data.reason, "title": edited.title,
            }], created_at=datetime.now(UTC),
        ))
        return reviews.save(batch, "case_manually_edited")

    @router.patch(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/cases/{stable_case_id}/status",
        response_model=CaseReviewBatch,
    )
    def change_case_status(
        project_id: int, batch_id: int, stable_case_id: str, data: CaseStatusChangeInput,
    ) -> CaseReviewBatch:
        _require_project(projects, project_id)
        batch = reviews.get(project_id, batch_id)
        if batch is None or batch.status != "confirmed":
            raise HTTPException(status_code=409, detail="只有已确认用例才能治理状态")
        current = next((item for item in latest_revisions(batch.revisions)
                        if item.stable_case_id == stable_case_id), None)
        if current is None:
            raise HTTPException(status_code=404, detail="稳定用例 ID 不存在")
        if data.lifecycle_status is None and data.participation_status is None:
            raise HTTPException(status_code=422, detail="至少提供一项状态变更")
        if data.lifecycle_status and not can_change_lifecycle(current.lifecycle_status, data.lifecycle_status):
            raise HTTPException(status_code=409, detail="不允许的用例生命周期迁移")
        previous_lifecycle = current.lifecycle_status
        previous_participation = current.participation_status
        if data.lifecycle_status:
            current.lifecycle_status = data.lifecycle_status
        if data.participation_status:
            current.participation_status = data.participation_status
        batch.status_changes.append(CaseStatusChangeRecord(
            stable_case_id=stable_case_id,
            previous_lifecycle_status=previous_lifecycle,
            lifecycle_status=current.lifecycle_status,
            previous_participation_status=previous_participation,
            participation_status=current.participation_status,
            reason=data.reason, confirmer_name=data.confirmer_name, changed_at=datetime.now(UTC),
        ))
        return reviews.save(batch, "case_status_changed")

    @router.patch(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/cases/bulk-status",
        response_model=CaseReviewBatch,
    )
    def change_case_statuses(
        project_id: int, batch_id: int, data: CaseBatchStatusInput,
    ) -> CaseReviewBatch:
        _require_project(projects, project_id)
        batch = reviews.get(project_id, batch_id)
        if batch is None or batch.status != "confirmed":
            raise HTTPException(status_code=409, detail="只有已确认用例才能批量治理状态")
        current_by_id = {item.stable_case_id: item for item in latest_revisions(batch.revisions)}
        missing = sorted(set(data.stable_case_ids) - set(current_by_id))
        if missing:
            raise HTTPException(status_code=404, detail={"code": "case_not_found", "ids": missing})
        for stable_case_id in data.stable_case_ids:
            current = current_by_id[stable_case_id]
            previous = current.participation_status
            current.participation_status = data.participation_status
            batch.status_changes.append(CaseStatusChangeRecord(
                stable_case_id=stable_case_id, previous_lifecycle_status=current.lifecycle_status,
                lifecycle_status=current.lifecycle_status, previous_participation_status=previous,
                participation_status=current.participation_status, reason=data.reason,
                confirmer_name=data.confirmer_name, changed_at=datetime.now(UTC),
            ))
        return reviews.save(batch, "case_statuses_batch_changed")

    @router.post(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/cases/{stable_case_id}/replace",
        response_model=CaseReviewBatch,
    )
    def replace_case(
        project_id: int, batch_id: int, stable_case_id: str, data: CaseReplacementInput,
    ) -> CaseReviewBatch:
        _require_project(projects, project_id)
        batch = reviews.get(project_id, batch_id)
        if batch is None or batch.status != "confirmed":
            raise HTTPException(status_code=409, detail="只有已确认用例才能创建被替代关系")
        previous = next((item for item in latest_revisions(batch.revisions)
                         if item.stable_case_id == stable_case_id), None)
        if previous is None or previous.lifecycle_status in {"deprecated", "superseded"}:
            raise HTTPException(status_code=409, detail="原用例不存在或已经结束生命周期")
        previous_lifecycle = previous.lifecycle_status
        previous_participation = previous.participation_status
        replacement_id = stable_id("case", f"{batch.id}:{data.candidate.id}:replacement")
        previous.lifecycle_status = "superseded"
        previous.superseded_by_case_id = replacement_id
        batch.status_changes.append(CaseStatusChangeRecord(
            stable_case_id=stable_case_id, previous_lifecycle_status=previous_lifecycle,
            lifecycle_status="superseded", previous_participation_status=previous_participation,
            participation_status=previous_participation, reason=data.reason,
            confirmer_name=data.confirmer_name, changed_at=datetime.now(UTC),
        ))
        batch.revisions.append(CaseRevision(
            id=stable_id("case-revision", f"{batch.id}:{data.candidate.id}:replacement"),
            candidate_id=data.candidate.id, revision=1, stable_case_id=replacement_id,
            external_case_number=data.candidate.external_case_number, lifecycle_status="effective",
            participation_status="included", candidate=data.candidate, review_notes=[data.reason],
            created_at=datetime.now(UTC),
        ))
        return reviews.save(batch, "case_replaced")

    @router.post("/api/projects/{project_id}/case-review-batches/{batch_id}/export")
    def export_cases(project_id: int, batch_id: int, data: CaseExportInput) -> Response:
        _require_project(projects, project_id)
        batch = reviews.get(project_id, batch_id)
        if batch is None or batch.status != "confirmed":
            raise HTTPException(status_code=409, detail="只有已确认用例才能下载用例文件")
        generation = generations.get(project_id, batch.generation_id)
        raw = templates.raw(project_id, generation.template_mapping_id) if generation else None
        mapping = templates.get(project_id, generation.template_mapping_id) if generation else None
        if mapping is None or raw is None or mapping.status != "confirmed":
            raise HTTPException(status_code=409, detail="模板映射未确认")
        content, media_type, extension = export_template(
            mapping, raw["content_base64"], batch.revisions, data.scope, data.stable_case_ids,
        )
        return Response(
            content=content, media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="test-cases.{extension}"'},
        )

    app.include_router(router)


def _require_project(repository: ProjectRepository, project_id: int) -> None:
    if repository.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")
