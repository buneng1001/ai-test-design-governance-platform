from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.case_lifecycle_service import export_template
from app.case_quality_service import STANDARD_COLUMNS, export_standard, quality_report, standard_rows
from app.case_review_review_routes import _require_project
from app.case_review_routes_context import CaseReviewRouteDependencies
from app.case_review_schemas import CaseExportInput, StandardCaseExportInput


def register_export_routes(router: APIRouter, deps: CaseReviewRouteDependencies) -> None:
    def confirmed_batch(project_id: int, batch_id: int):
        _require_project(deps, project_id)
        batch = deps.reviews.get(project_id, batch_id)
        if batch is None or batch.status != "confirmed":
            raise HTTPException(status_code=409, detail="只有已确认用例才能执行质量检查或导出")
        return batch

    @router.post("/api/projects/{project_id}/case-review-batches/{batch_id}/export")
    def export_cases(project_id: int, batch_id: int, data: CaseExportInput) -> Response:
        batch = confirmed_batch(project_id, batch_id)
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

    @router.get("/api/projects/{project_id}/case-review-batches/{batch_id}/quality-checks")
    def quality_checks(project_id: int, batch_id: int) -> dict:
        batch = confirmed_batch(project_id, batch_id)
        generation = deps.generations.get(project_id, batch.generation_id)
        review = deps.requirement_reviews.latest_for_version(
            project_id, generation.requirement_version_id if generation else 0,
        )
        if generation is None or review is None:
            raise HTTPException(status_code=409, detail="候选用例缺少需求审核上下文")
        return quality_report(review, batch.revisions)

    @router.get("/api/projects/{project_id}/case-review-batches/{batch_id}/standard-preview")
    def standard_preview(project_id: int, batch_id: int) -> dict:
        batch = confirmed_batch(project_id, batch_id)
        project = deps.projects.get(project_id)
        return {"columns": STANDARD_COLUMNS, "rows": standard_rows(batch.revisions, project.software_version)}

    @router.post("/api/projects/{project_id}/case-review-batches/{batch_id}/standard-export")
    def standard_export(project_id: int, batch_id: int, data: StandardCaseExportInput) -> Response:
        batch = confirmed_batch(project_id, batch_id)
        project = deps.projects.get(project_id)
        rows = standard_rows(batch.revisions, project.software_version)
        if data.scope == "selected":
            selected = set(data.stable_case_ids)
            rows = [row for row in rows if row["stable_case_id"] in selected]
        elif data.scope == "changed":
            revisions = {item.stable_case_id: item for item in batch.revisions if item.stable_case_id}
            rows = [row for row in rows if revisions[row["stable_case_id"]].revision > 1]
        content, media_type, extension = export_standard(rows, data.format)
        return Response(content=content, media_type=media_type, headers={
            "Content-Disposition": f'attachment; filename="standard-test-cases.{extension}"',
        })
