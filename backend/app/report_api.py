import json

from fastapi import FastAPI, HTTPException, Response, status

from app.report_schemas import ReportDocument
from app.report_service import ReportService
from app.repository import ProjectRepository


def register_report_routes(app: FastAPI, repository: ProjectRepository, service: ReportService) -> None:
    @app.get("/api/projects/{project_id}/reports/test-design", response_model=ReportDocument)
    def get_test_design_report(project_id: int) -> dict:
        _require_project(repository, project_id)
        return service.build_test_design(project_id)

    @app.get("/api/projects/{project_id}/reports/execution-governance", response_model=ReportDocument)
    def get_execution_governance_report(project_id: int) -> dict:
        _require_project(repository, project_id)
        return service.build_execution_governance(project_id)

    @app.get("/api/projects/{project_id}/reports/audit-package", response_model=ReportDocument)
    def get_audit_package(project_id: int) -> dict:
        _require_project(repository, project_id)
        return service.build_audit_package(project_id)

    @app.get("/api/projects/{project_id}/reports/{report_type}/download")
    def download_report(project_id: int, report_type: str) -> Response:
        _require_project(repository, project_id)
        builders = {
            "test-design": service.build_test_design,
            "execution-governance": service.build_execution_governance,
            "audit-package": service.build_audit_package,
        }
        builder = builders.get(report_type)
        if builder is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告类型不存在")
        payload = json.dumps(builder(project_id), ensure_ascii=False, indent=2)
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{report_type}-{project_id}.json"'},
        )


def _require_project(repository: ProjectRepository, project_id: int) -> None:
    if repository.get(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试设计项目不存在")
