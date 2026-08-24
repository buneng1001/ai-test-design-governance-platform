import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.schemas import Project, ProjectInput, ProjectSettings


MIGRATIONS = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        test_object TEXT NOT NULL,
        description TEXT NOT NULL,
        settings_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
)


class ProjectRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def migrate(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(MIGRATIONS[0])
            applied_versions = {
                row["version"] for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for version, migration in enumerate(MIGRATIONS[1:], start=1):
                if version in applied_versions:
                    continue
                connection.executescript(migration)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, self._now()),
                )

    def create(self, project_input: ProjectInput) -> Project:
        now = self._now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects(name, test_object, description, settings_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_input.name,
                    project_input.test_object,
                    project_input.description,
                    project_input.settings.model_dump_json(),
                    now,
                    now,
                ),
            )
            project_id = cursor.lastrowid
        project = self.get(project_id)
        assert project is not None
        return project

    def list(self) -> list[Project]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY created_at DESC, id DESC").fetchall()
        return [self._to_project(row) for row in rows]

    def get(self, project_id: int | None) -> Project | None:
        if project_id is None:
            return None
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._to_project(row) if row else None

    def update(self, project_id: int, project_input: ProjectInput) -> Project | None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET name = ?, test_object = ?, description = ?, settings_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    project_input.name,
                    project_input.test_object,
                    project_input.description,
                    project_input.settings.model_dump_json(),
                    self._now(),
                    project_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(project_id)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _to_project(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            test_object=row["test_object"],
            description=row["description"],
            settings=ProjectSettings.model_validate(json.loads(row["settings_json"])),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

