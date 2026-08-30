from fastapi import FastAPI, HTTPException, status

from app.asset_repository import AssetRepository
from app.asset_schemas import AssetContentInput, AssetProvenanceInput, AssetProvenanceRecord, HashVerification
from app.main_route_context import AppRouteContext
from app.repository import ProjectRepository
from app.schemas import Project, ProjectInput


def require_project(project: Project | None) -> Project:
    """保留项目不存在时的统一错误语义。"""
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试设计项目不存在")
    return project


def require_asset(asset: AssetProvenanceRecord | None) -> AssetProvenanceRecord:
    """保留资产不存在时的统一错误语义。"""
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产来源记录不存在")
    return asset


def register_project_asset_routes(app: FastAPI, context: AppRouteContext) -> None:
    """注册基础项目和资产接口。"""
    repository: ProjectRepository = context.repository
    asset_repository: AssetRepository = context.asset_repository

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

    @app.get("/api/projects/{project_id}/assets/{asset_id}/history", response_model=list[AssetProvenanceRecord])
    def get_asset_history(project_id: int, asset_id: int) -> list[AssetProvenanceRecord]:
        require_project(repository.get(project_id))
        history = asset_repository.history(project_id, asset_id)
        if history is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产来源记录不存在")
        return history

    @app.post("/api/projects/{project_id}/assets/{asset_id}/verify", response_model=HashVerification)
    def verify_asset_hash(project_id: int, asset_id: int, content: AssetContentInput) -> HashVerification:
        require_project(repository.get(project_id))
        asset = require_asset(asset_repository.get(project_id, asset_id))
        actual_sha256 = asset_repository.hash_content(content.content_base64)
        return HashVerification(
            matches=asset.sha256 == actual_sha256,
            expected_sha256=asset.sha256,
            actual_sha256=actual_sha256,
        )

    @app.get("/api/projects/{project_id}/model-context-assets", response_model=list[AssetProvenanceRecord])
    def get_model_context_assets(project_id: int) -> list[AssetProvenanceRecord]:
        require_project(repository.get(project_id))
        return asset_repository.model_context_assets(project_id)
