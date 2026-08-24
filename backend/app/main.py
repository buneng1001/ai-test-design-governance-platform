import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.asset_repository import AssetRepository
from app.asset_schemas import (
    AssetContentInput,
    AssetProvenanceInput,
    AssetProvenanceRecord,
    HashVerification,
)
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.requirement_schemas import RequirementPackage, RequirementPackageInput, RequirementVersion
from app.requirement_service import build_requirement_package
from app.schemas import Project, ProjectInput


def create_app(database_path: Path | None = None) -> FastAPI:
    resolved_database_path = database_path or Path(os.getenv("APP_DATABASE_PATH", "data/app.db"))
    repository = ProjectRepository(resolved_database_path)
    asset_repository = AssetRepository(resolved_database_path)
    requirement_repository = RequirementRepository(resolved_database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        repository.migrate()
        yield

    app = FastAPI(title="AI 测试设计与治理平台", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
    def create_project(project_input: ProjectInput) -> Project:
        return repository.create(project_input)

    @app.get("/api/projects", response_model=list[Project])
    def list_projects() -> list[Project]:
        return repository.list()

    @app.get("/api/projects/{project_id}", response_model=Project)
    def get_project(project_id: int) -> Project:
        return require_project(repository.get(project_id))

    @app.put("/api/projects/{project_id}", response_model=Project)
    def update_project(project_id: int, project_input: ProjectInput) -> Project:
        return require_project(repository.update(project_id, project_input))

    @app.post(
        "/api/projects/{project_id}/assets",
        response_model=AssetProvenanceRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def create_asset(project_id: int, asset_input: AssetProvenanceInput) -> AssetProvenanceRecord:
        require_project(repository.get(project_id))
        return asset_repository.create(project_id, asset_input)

    @app.get("/api/projects/{project_id}/assets", response_model=list[AssetProvenanceRecord])
    def list_assets(project_id: int) -> list[AssetProvenanceRecord]:
        require_project(repository.get(project_id))
        return asset_repository.list_assets(project_id)

    @app.put("/api/projects/{project_id}/assets/{asset_id}", response_model=AssetProvenanceRecord)
    def revise_asset(
        project_id: int,
        asset_id: int,
        asset_input: AssetProvenanceInput,
    ) -> AssetProvenanceRecord:
        require_project(repository.get(project_id))
        return require_asset(asset_repository.revise(project_id, asset_id, asset_input))

    @app.get(
        "/api/projects/{project_id}/assets/{asset_id}/history",
        response_model=list[AssetProvenanceRecord],
    )
    def get_asset_history(project_id: int, asset_id: int) -> list[AssetProvenanceRecord]:
        require_project(repository.get(project_id))
        history = asset_repository.history(project_id, asset_id)
        if history is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产来源记录不存在")
        return history

    @app.post(
        "/api/projects/{project_id}/assets/{asset_id}/verify",
        response_model=HashVerification,
    )
    def verify_asset_hash(
        project_id: int,
        asset_id: int,
        content: AssetContentInput,
    ) -> HashVerification:
        require_project(repository.get(project_id))
        asset = require_asset(asset_repository.get(project_id, asset_id))
        actual_sha256 = asset_repository.hash_content(content.content_base64)
        return HashVerification(
            matches=asset.sha256 == actual_sha256,
            expected_sha256=asset.sha256,
            actual_sha256=actual_sha256,
        )

    @app.get(
        "/api/projects/{project_id}/model-context-assets",
        response_model=list[AssetProvenanceRecord],
    )
    def get_model_context_assets(project_id: int) -> list[AssetProvenanceRecord]:
        require_project(repository.get(project_id))
        return asset_repository.model_context_assets(project_id)

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

    @app.get(
        "/api/projects/{project_id}/requirement-packages/{package_id}",
        response_model=RequirementPackage,
    )
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

    @app.get(
        "/api/projects/{project_id}/requirement-versions",
        response_model=list[RequirementVersion],
    )
    def list_requirement_versions(project_id: int) -> list[RequirementVersion]:
        require_project(repository.get(project_id))
        return requirement_repository.list_versions(project_id)

    @app.get(
        "/api/projects/{project_id}/requirement-versions/{version_id}",
        response_model=RequirementVersion,
    )
    def get_requirement_version(project_id: int, version_id: int) -> RequirementVersion:
        require_project(repository.get(project_id))
        version = requirement_repository.get_version(project_id, version_id)
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="需求版本不存在")
        return version

    return app


def require_project(project: Project | None) -> Project:
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试设计项目不存在")
    return project


def require_asset(asset: AssetProvenanceRecord | None) -> AssetProvenanceRecord:
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产来源记录不存在")
    return asset


app = create_app()
