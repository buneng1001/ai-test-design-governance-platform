import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.execution_batch_schemas import ExecutionBatch


class ExecutionBatchRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def create(self, batch: ExecutionBatch) -> ExecutionBatch:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO execution_batches(project_id, test_task_id, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (batch.project_id, batch.test_task_id, batch.model_dump_json(), datetime.now(UTC).isoformat()),
            )
            batch.id = cursor.lastrowid or 0
            connection.execute(
                "UPDATE execution_batches SET payload_json = ? WHERE id = ?",
                (batch.model_dump_json(), batch.id),
            )
        return batch

    def allocate_sequences(self, project_id: int, stable_case_ids: list[str]) -> dict[str, int]:
        """在写事务中分配序号，避免重复请求或并发创建覆盖历史记录。"""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            sequences: dict[str, int] = {}
            for stable_case_id in stable_case_ids:
                row = connection.execute(
                    "SELECT COALESCE(MAX(execution_sequence), 0) + 1 AS next_sequence "
                    "FROM execution_records WHERE project_id = ? AND stable_case_id = ?",
                    (project_id, stable_case_id),
                ).fetchone()
                sequence = int(row["next_sequence"])
                connection.execute(
                    "INSERT INTO execution_records(project_id, stable_case_id, execution_sequence) "
                    "VALUES (?, ?, ?)",
                    (project_id, stable_case_id, sequence),
                )
                sequences[stable_case_id] = sequence
        return sequences

    def get(self, project_id: int, batch_id: int) -> ExecutionBatch | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM execution_batches WHERE id = ? AND project_id = ?",
                (batch_id, project_id),
            ).fetchone()
        return ExecutionBatch.model_validate_json(row["payload_json"]) if row else None

    def list(self, project_id: int) -> list[ExecutionBatch]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM execution_batches WHERE project_id = ? ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        return [ExecutionBatch.model_validate_json(row["payload_json"]) for row in rows]
