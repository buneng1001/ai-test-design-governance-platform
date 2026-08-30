from fastapi import FastAPI, HTTPException, status

from app.asset_repository import AssetRepository
from app.main_route_context import AppRouteContext
from app.requirement_repository import RequirementRepository
from app.requirement_schemas import RequirementPackage, RequirementPackageInput, RequirementVersion
from app.requirement_service import build_requirement_package
from app.repository import ProjectRepository
from app.schemas import Project
from app.project_asset_api import require_project


def register_requirement_routes(app: FastAPI, context: AppRouteContext) -> None:
    """注册需求资料包和需求版本接口。"""
    repository: ProjectRepository = context.repository
    asset_repository: AssetRepository = context.asset_repository
    requirement_repository: RequirementRepository = context.requirement_repository

    @app.post(
        "/api/projects/{project_id}/requirement-packages",
        response_model=RequirementPackage,
        status_code=status.HTTP_201_CREATED,
    )
    def create_requirement_package(
        project_id: int,
        package_input: RequirementPackageInput,
    ) -> RequirementPackage:
        require_project(repository.get(project_id))
        package = build_requirement_package(project_id, package_input, asset_repository)
        return requirement_repository.create_package(package)

    @app.get("/api/projects/{project_id}/requirement-packages/{package_id}", response_model=RequirementPackage)
    def get_requirement_package(project_id: int, package_id: int) -> RequirementPackage:
        require_project(repository.get(project_id))
        package = requirement_repository.get_package(project_id, package_id)
        if package is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="需求资料包不存在")
        return package

    @app.post(
        "/api/projects/{project_id}/requirement-packages/{package_id}/publish",
        response_model=RequirementVersion,
        status_code=status.HTTP_201_CREATED,
    )
    def publish_requirement_package(project_id: int, package_id: int) -> RequirementVersion:
        require_project(repository.get(project_id))
        package = requirement_repository.get_package(project_id, package_id)
        if package is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="需求资料包不存在")
        if package.published_version_id is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="需求资料包已经发布")
        if not any(material.parse_status in {"complete", "partial"} for material in package.materials):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="需求资料包没有可发布的完整解析结果",
            )
        version = requirement_repository.publish(package)
        if version is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="需求资料包已经发布")
        return version

    @app.get("/api/projects/{project_id}/requirement-versions", response_model=list[RequirementVersion])
    def list_requirement_versions(project_id: int) -> list[RequirementVersion]:
        require_project(repository.get(project_id))
        return requirement_repository.list_versions(project_id)

    @app.get("/api/projects/{project_id}/requirement-versions/{version_id}", response_model=RequirementVersion)
    def get_requirement_version(project_id: int, version_id: int) -> RequirementVersion:
        require_project(repository.get(project_id))
        version = requirement_repository.get_version(project_id, version_id)
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="需求版本不存在")
        return version
