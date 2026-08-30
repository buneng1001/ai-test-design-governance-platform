from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.case_lifecycle_service import latest_revisions
from app.case_review_review_routes import _require_project
from app.case_review_routes_context import CaseReviewRouteDependencies
from app.case_review_schemas import CaseReplacementInput, CaseReviewBatch, CaseRevision, CaseStatusChangeRecord
from app.design_service import stable_id


def register_replacement_routes(router: APIRouter, deps: CaseReviewRouteDependencies) -> None:
    @router.post(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/cases/{stable_case_id}/replace",
        response_model=CaseReviewBatch,
    )
    def replace_case(
        project_id: int, batch_id: int, stable_case_id: str, data: CaseReplacementInput,
    ) -> CaseReviewBatch:
        _require_project(deps, project_id)
        batch = deps.reviews.get(project_id, batch_id)
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
        return deps.reviews.save(batch, "case_replaced")
