from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.case_lifecycle_service import export_template
from app.case_review_review_routes import _require_project
from app.case_review_routes_context import CaseReviewRouteDependencies
from app.case_review_schemas import CaseExportInput


def register_export_routes(router: APIRouter, deps: CaseReviewRouteDependencies) -> None:
    @router.post("/api/projects/{project_id}/case-review-batches/{batch_id}/export")
    def export_cases(project_id: int, batch_id: int, data: CaseExportInput) -> Response:
        _require_project(deps, project_id)
        batch = deps.reviews.get(project_id, batch_id)
        if batch is None or batch.status != "confirmed":
            raise HTTPException(status_code=409, detail="只有已确认用例才能下载用例文件")
        generation = deps.generations.get(project_id, batch.generation_id)
        raw = deps.templates.raw(project_id, generation.template_mapping_id) if generation else None
        mapping = deps.templates.get(project_id, generation.template_mapping_id) if generation else None
        if mapping is None or raw is None or mapping.status != "confirmed":
            raise HTTPException(status_code=409, detail="模板映射未确认")
        content, media_type, extension = export_template(
            mapping, raw["content_base64"], batch.revisions, data.scope, data.stable_case_ids,
        )
        return Response(
            content=content, media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="test-cases.{extension}"'},
        )
