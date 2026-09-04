import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.repository import MIGRATIONS
from app.schemas import Project, ProjectInput, ProjectSettings


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
            self._ensure_ai_attempt_diagnostic(connection)

    @staticmethod
    def _ensure_ai_attempt_diagnostic(connection: sqlite3.Connection) -> None:
        """按实际表结构补齐历史迁移可能漏掉的 AI 运行诊断字段。"""
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_run_attempts)")}
        if "diagnostic" not in columns:
            connection.execute("ALTER TABLE ai_run_attempts ADD COLUMN diagnostic TEXT")

    def create(self, project_input: ProjectInput) -> Project:
        now = self._now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects(
                    name, test_object, software_version, description, settings_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_input.name,
                    project_input.test_object,
                    project_input.software_version,
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
                SET name = ?, test_object = ?, software_version = ?, description = ?, settings_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    project_input.name,
                    project_input.test_object,
                    project_input.software_version,
                    project_input.description,
                    project_input.settings.model_dump_json(),
                    self._now(),
                    project_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(project_id)

    def delete(self, project_id: int) -> bool:
        """删除项目及其业务数据，保留跨项目的模型配置。"""
        with self.connect() as connection:
            if connection.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                return False
            connection.execute("DELETE FROM requirement_analysis_history WHERE analysis_id IN "
                               "(SELECT id FROM requirement_analyses WHERE project_id = ?)", (project_id,))
            connection.execute("DELETE FROM test_design_history WHERE design_id IN "
                               "(SELECT id FROM test_designs WHERE project_id = ?)", (project_id,))
            connection.execute("DELETE FROM template_mapping_history WHERE mapping_id IN "
                               "(SELECT id FROM template_mappings WHERE project_id = ?)", (project_id,))
            connection.execute("DELETE FROM case_review_history WHERE batch_id IN "
                               "(SELECT id FROM case_review_batches WHERE project_id = ?)", (project_id,))
            connection.execute("DELETE FROM ai_run_dispositions WHERE run_id IN "
                               "(SELECT id FROM ai_runs WHERE project_id = ?)", (project_id,))
            connection.execute("DELETE FROM ai_run_attempts WHERE run_id IN "
                               "(SELECT id FROM ai_runs WHERE project_id = ?)", (project_id,))
            connection.execute("DELETE FROM change_impact_history WHERE analysis_id IN "
                               "(SELECT id FROM change_impact_analyses WHERE project_id = ?)", (project_id,))
            connection.execute("DELETE FROM execution_batch_conclusions WHERE batch_id IN "
                               "(SELECT id FROM execution_batches WHERE project_id = ?)", (project_id,))
            for table in (
                "requirement_analyses", "test_designs", "template_mappings", "case_review_batches",
                "case_generations", "ai_runs", "test_tasks", "execution_result_conflicts",
                "execution_result_records", "execution_records", "execution_batches", "regression_selections",
                "change_impact_analyses", "quality_issue_references", "defect_patterns", "ai_evaluation_runs",
            ):
                connection.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM asset_provenance_revisions WHERE asset_id IN "
                               "(SELECT id FROM assets WHERE project_id = ?)", (project_id,))
            connection.execute("DELETE FROM assets WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM requirement_versions WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM requirement_packages WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return True

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _to_project(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            test_object=row["test_object"],
            software_version=row["software_version"],
            description=row["description"],
            settings=ProjectSettings.model_validate(json.loads(row["settings_json"])),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
