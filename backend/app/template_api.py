import base64
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Response, status

from app.repository import ProjectRepository
from app.template_repository import TemplateMappingRepository
from app.template_schemas import (
    TemplateConfirmationInput,
    TemplateMappingVersion,
    TemplateUploadInput,
    TemplateValidationResult,
)
from app.template_service import inspect_template, suggested_mapping, validate_mappings


def register_template_routes(
    app: FastAPI, repository: ProjectRepository, template_repository: TemplateMappingRepository
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/template-mappings",
        response_model=TemplateMappingVersion,
        status_code=status.HTTP_201_CREATED,
    )
    def upload_template(project_id: int, data: TemplateUploadInput) -> TemplateMappingVersion:
        _require_project(repository, project_id)
        try:
            template_format, sheets, diagnostics = inspect_template(data.filename, data.content_base64)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        for sheet in sheets:
            sheet.field_mapping = suggested_mapping(sheet)
        mapping = TemplateMappingVersion(
            id=0, project_id=project_id, version=0, filename=data.filename, format=template_format,
            sheets=sheets, diagnostics=diagnostics, retained_sheet_names=[sheet.name for sheet in sheets],
        )
        return template_repository.create(mapping, data.content_base64)

    @router.get("/api/projects/{project_id}/template-mappings", response_model=list[TemplateMappingVersion])
    def list_templates(project_id: int) -> list[TemplateMappingVersion]:
        _require_project(repository, project_id)
        return template_repository.list_versions(project_id)

    @router.get("/api/projects/{project_id}/template-mappings/{mapping_id}", response_model=TemplateMappingVersion)
    def get_template(project_id: int, mapping_id: int) -> TemplateMappingVersion:
        _require_project(repository, project_id)
        return _require_mapping(template_repository.get(project_id, mapping_id))

    @router.get("/api/projects/{project_id}/template-mappings/{mapping_id}/history")
    def get_template_history(project_id: int, mapping_id: int) -> list[dict]:
        _require_project(repository, project_id)
        history = template_repository.history(project_id, mapping_id)
        if history is None:
            raise HTTPException(status_code=404, detail="用例模板映射不存在")
        return history

    @router.post(
        "/api/projects/{project_id}/template-mappings/{mapping_id}/validate",
        response_model=TemplateValidationResult,
    )
    def validate_template(
        project_id: int, mapping_id: int, data: TemplateConfirmationInput
    ) -> TemplateValidationResult:
        _require_project(repository, project_id)
        mapping = _require_mapping(template_repository.get(project_id, mapping_id))
        candidate = mapping.model_copy(deep=True)
        _apply_mappings(candidate, data)
        return validate_mappings(candidate.sheets)

    @router.post(
        "/api/projects/{project_id}/template-mappings/{mapping_id}/confirm",
        response_model=TemplateMappingVersion,
    )
    def confirm_template(project_id: int, mapping_id: int, data: TemplateConfirmationInput) -> TemplateMappingVersion:
        _require_project(repository, project_id)
        mapping = _require_mapping(template_repository.get(project_id, mapping_id))
        if mapping.status == "confirmed":
            raise HTTPException(status_code=409, detail="模板映射已经确认，不能覆盖")
        _apply_mappings(mapping, data)
        validation = validate_mappings(mapping.sheets)
        if not validation.valid:
            raise HTTPException(status_code=422, detail=[item.model_dump() for item in validation.diagnostics])
        mapping.confirmed_by = data.confirmer_name
        raw = template_repository.raw(project_id, mapping_id)
        assert raw is not None
        return template_repository.confirm(mapping, raw["content_base64"])

    @router.get("/api/projects/{project_id}/template-mappings/{mapping_id}/export")
    def export_template(project_id: int, mapping_id: int) -> Response:
        _require_project(repository, project_id)
        mapping = _require_mapping(template_repository.get(project_id, mapping_id))
        if mapping.status != "confirmed":
            raise HTTPException(status_code=409, detail="模板映射确认后才能导出")
        raw = template_repository.raw(project_id, mapping_id)
        assert raw is not None
        content = base64.b64decode(raw["content_base64"])
        media_type = (
            "text/csv" if mapping.format == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        disposition = f"attachment; filename=template.{mapping.format}; filename*=UTF-8''{quote(mapping.filename)}"
        return Response(content=content, media_type=media_type, headers={"Content-Disposition": disposition})

    app.include_router(router)


def _apply_mappings(mapping: TemplateMappingVersion, data: TemplateConfirmationInput) -> None:
    by_name = {sheet.name: sheet for sheet in mapping.sheets}
    if set(by_name) != {item.sheet_name for item in data.mappings}:
        raise HTTPException(status_code=422, detail="必须逐表确认每一张工作表")
    for item in data.mappings:
        sheet = by_name[item.sheet_name]
        sheet.role = item.role
        sheet.participates = item.participates
        sheet.title_row = item.title_row
        sheet.field_mapping = item.field_mapping


def _require_project(repository: ProjectRepository, project_id: int) -> None:
    if repository.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")


def _require_mapping(mapping: TemplateMappingVersion | None) -> TemplateMappingVersion:
    if mapping is None:
        raise HTTPException(status_code=404, detail="用例模板映射不存在")
    return mapping
