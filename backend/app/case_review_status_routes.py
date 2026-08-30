from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.case_review_routes_context import CaseReviewRouteDependencies
from app.case_review_schemas import CaseBatchStatusInput, CaseReviewBatch, CaseStatusChangeInput, CaseStatusChangeRecord
from app.case_lifecycle_service import can_change_lifecycle, latest_revisions
from app.case_review_review_routes import _require_project


def register_status_routes(router: APIRouter, deps: CaseReviewRouteDependencies) -> None:
    @router.patch(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/cases/{stable_case_id}/status",
        response_model=CaseReviewBatch,
    )
    def change_case_status(
        project_id: int, batch_id: int, stable_case_id: str, data: CaseStatusChangeInput,
    ) -> CaseReviewBatch:
        _require_project(deps, project_id)
        batch = deps.reviews.get(project_id, batch_id)
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
            stable_case_id=stable_case_id, previous_lifecycle_status=previous_lifecycle,
            lifecycle_status=current.lifecycle_status, previous_participation_status=previous_participation,
            participation_status=current.participation_status, reason=data.reason,
            confirmer_name=data.confirmer_name, changed_at=datetime.now(UTC),
        ))
        return deps.reviews.save(batch, "case_status_changed")

    @router.patch(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/cases/bulk-status",
        response_model=CaseReviewBatch,
    )
    def change_case_statuses(
        project_id: int, batch_id: int, data: CaseBatchStatusInput,
    ) -> CaseReviewBatch:
        _require_project(deps, project_id)
        batch = deps.reviews.get(project_id, batch_id)
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
        return deps.reviews.save(batch, "case_statuses_batch_changed")
