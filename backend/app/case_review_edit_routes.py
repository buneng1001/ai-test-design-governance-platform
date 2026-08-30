from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.case_review_routes_context import CaseReviewRouteDependencies
from app.case_review_schemas import CaseEditInput, CaseReviewBatch, CaseRevision
from app.design_service import stable_id
from app.case_review_review_routes import _require_project


def register_edit_routes(router: APIRouter, deps: CaseReviewRouteDependencies) -> None:
    @router.patch(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/cases/{case_id}",
        response_model=CaseReviewBatch,
    )
    def edit_case(project_id: int, batch_id: int, case_id: str, data: CaseEditInput) -> CaseReviewBatch:
        """保存人工修订，并保留原始 AI 候选。"""
        _require_project(deps, project_id)
        batch = deps.reviews.get(project_id, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="评审批次不存在")
        generation = deps.generations.get(project_id, batch.generation_id)
        if generation is None:
            raise HTTPException(status_code=404, detail="候选测试用例生成记录不存在")
        # 编辑确认前的草稿修订还没有稳定用例 ID，恢复时也必须能找到它。
        previous = max(
            (
                item for item in batch.revisions
                if item.stable_case_id == case_id or item.candidate_id == case_id
            ),
            key=lambda item: item.revision, default=None,
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
            candidate=edited, original_candidate=original_candidate, manual_modified=True,
            edit_history=(previous.edit_history if previous else []) + [{
                "reason": data.reason, "title": edited.title,
            }], created_at=datetime.now(UTC),
        ))
        return deps.reviews.save(batch, "case_manually_edited")
