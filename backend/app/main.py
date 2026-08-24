import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.repository import ProjectRepository
from app.schemas import Project, ProjectInput


def create_app(database_path: Path | None = None) -> FastAPI:
    resolved_database_path = database_path or Path(os.getenv("APP_DATABASE_PATH", "data/app.db"))
    repository = ProjectRepository(resolved_database_path)

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

    return app


def require_project(project: Project | None) -> Project:
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试设计项目不存在")
    return project


app = create_app()
