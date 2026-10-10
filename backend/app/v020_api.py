from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.responses import Response

from app.asset_repository import AssetRepository
from app.asset_schemas import AssetProvenanceInput
from app.project_repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.requirement_schemas import RequirementFileInput, RequirementPackageInput
from app.requirement_service import build_requirement_package
from app.v020_delivery import build_delivery_package
from app.v020_export import build_page_export
from app.v020_repository import V020Repository
from app.v020_run_schemas import TemplateSelectionInput
from app.v020_schemas import ArchiveInput, MaterialUploadInput, ProjectSummary
from app.case_lifecycle_service import default_template
from app.template_repository import TemplateMappingRepository


def register_v020_routes(
    app: FastAPI,
    projects: ProjectRepository,
    assets: AssetRepository,
    requirements: RequirementRepository,
    workspace: V020Repository,
    templates: TemplateMappingRepository,
) -> None:
    router = APIRouter(prefix="/api/v0.2")

    @router.get("/projects", response_model=list[ProjectSummary])
    def list_projects(archived: bool = False) -> list[dict]:
        return workspace.list_project_summaries(archived)

    @router.patch("/projects/{project_id}/archive")
    def archive_project(project_id: int, data: ArchiveInput) -> dict:
        project = projects.set_archived(project_id, data.archived)
        if project is None:
            raise HTTPException(status_code=404, detail="测试设计项目不存在")
        return project.model_dump(mode="json")

    @router.post("/projects/{project_id}/materials", status_code=status.HTTP_201_CREATED)
    def upload_materials(project_id: int, data: MaterialUploadInput) -> dict:
        project = projects.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="测试设计项目不存在")
        registered = []
        for item in data.files:
            registered.append(assets.create(project_id, AssetProvenanceInput(
                name=item.filename,
                media_type=item.media_type,
                asset_type="requirement_material",
                provenance_kind="original_synthetic",
                source="用户上传",
                usage_permission="project_owned",
                model_permission="allowed",
                requirement_version="当前资料版本",
                purpose="上传页本地解析（本页面不调用 AI）",
                content_base64=item.content_base64,
                change_reason="上传并解析",
            )))
        package = requirements.create_package(build_requirement_package(
            project_id,
            RequirementPackageInput(name="上传并解析资料", files=[RequirementFileInput(
                asset_id=record.id,
                filename=record.name,
                media_type=record.media_type,
            ) for record in registered]),
            assets,
        ))
        usable = any(item.parse_status in {"complete", "partial"} for item in package.materials)
        version = requirements.publish(package) if usable else None
        workspace.save_workspace(
            project_id,
            supplemental_notes=data.supplemental_notes,
            active_requirement_version_id=version.id if version else None,
        )
        return {
            "ai_called": False,
            "supplemental_notes": data.supplemental_notes,
            "requirement_package": package.model_dump(mode="json"),
            "requirement_version": version.model_dump(mode="json") if version else None,
        }

    @router.get("/projects/{project_id}/workspace")
    def get_workspace(project_id: int) -> dict:
        if projects.get(project_id) is None:
            raise HTTPException(status_code=404, detail="测试设计项目不存在")
        state = workspace.workspace_row(project_id)
        version = requirements.get_version(project_id, state["active_requirement_version_id"])
        return {
            "project_id": project_id,
            "supplemental_notes": state["supplemental_notes"],
            "requirement_version": version.model_dump(mode="json") if version else None,
            "template": {
                "mode": state["template_mode"],
                "mapping_id": state["template_mapping_id"],
            },
            "analysis_rows": workspace.list_payloads("v020_analysis_rows", project_id),
            "suggestions": workspace.list_payloads("v020_suggestions", project_id),
            "review_suggestions": workspace.list_payloads("v020_review_suggestions", project_id),
            "cases": workspace.list_payloads("v020_cases", project_id),
            "case_generations": workspace.case_generations(project_id),
            "runs": workspace.list_payloads("v020_runs", project_id),
            "exports": workspace.export_history(project_id),
        }

    @router.get("/projects/{project_id}/delivery-package")
    def download_delivery_package(project_id: int) -> Response:
        try:
            content = build_delivery_package(project_id, projects, requirements, workspace)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="project-{project_id}-delivery.zip"'},
        )

    @router.get("/projects/{project_id}/case-template")
    def get_case_template(project_id: int) -> dict:
        if projects.get(project_id) is None:
            raise HTTPException(status_code=404, detail="测试设计项目不存在")
        state = workspace.workspace_row(project_id)
        if state["template_mode"] == "uploaded" and state["template_mapping_id"]:
            mapping = templates.get(project_id, state["template_mapping_id"])
        else:
            mapping, _ = default_template(project_id)
        return {"mode": state["template_mode"], "mapping": mapping.model_dump(mode="json") if mapping else None}

    @router.put("/projects/{project_id}/case-template")
    def select_case_template(project_id: int, data: TemplateSelectionInput) -> dict:
        if projects.get(project_id) is None:
            raise HTTPException(status_code=404, detail="测试设计项目不存在")
        if data.mode == "uploaded":
            mapping = templates.get(project_id, data.mapping_id or 0)
            if mapping is None or mapping.status != "confirmed":
                raise HTTPException(status_code=409, detail="上传模板尚未完成字段解析与映射确认")
        else:
            mapping, _ = default_template(project_id)
        workspace.save_template(project_id, data.mode, data.mapping_id if data.mode == "uploaded" else None)
        return {"mode": data.mode, "mapping": mapping.model_dump(mode="json")}

    @router.get("/projects/{project_id}/exports/{page}")
    def export_page(
        project_id: int,
        page: Literal["upload", "analysis", "suggestions", "review", "cases"],
        format: Literal["json", "xlsx"] = "json",
        run_id: str | None = None,
    ) -> Response:
        if projects.get(project_id) is None:
            raise HTTPException(status_code=404, detail="测试设计项目不存在")
        if page == "upload" and format == "xlsx":
            raise HTTPException(status_code=422, detail="解析结果仅提供 JSON 结构和来源清单")
        content, media_type, filename = build_page_export(
            project_id, page, format, workspace, requirements, run_id,
        )
        workspace.record_export(project_id, page, format, filename, run_id)
        return Response(content=content, media_type=media_type,
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    app.include_router(router)
