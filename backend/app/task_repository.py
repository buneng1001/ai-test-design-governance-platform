import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.task_schemas import TestTask


class TestTaskRepository:
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

    def create(self, task: TestTask) -> TestTask:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO test_tasks(project_id, batch_id, task_id, task_version, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    task.project_id,
                    task.case_review_batch_id,
                    task.task_id,
                    task.task_version,
                    task.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("测试任务保存失败")
        return task

    def get(self, project_id: int, task_id: str, task_version: int | None = None) -> TestTask | None:
        query = "SELECT payload_json FROM test_tasks WHERE project_id = ? AND task_id = ?"
        parameters: tuple[object, ...] = (project_id, task_id)
        if task_version is not None:
            query += " AND task_version = ?"
            parameters += (task_version,)
        query += " ORDER BY task_version DESC LIMIT 1"
        with self.connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return TestTask.model_validate_json(row["payload_json"]) if row else None

    def list_for_project(self, project_id: int) -> list[TestTask]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM test_tasks WHERE project_id = ? ORDER BY id", (project_id,)
            ).fetchall()
        return [TestTask.model_validate_json(row["payload_json"]) for row in rows]
