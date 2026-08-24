import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.case_review_schemas import CaseReviewBatch


class CaseReviewRepository:
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

    def create(self, batch: CaseReviewBatch) -> CaseReviewBatch:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO case_review_batches(project_id, generation_id, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (batch.project_id, batch.generation_id, batch.model_dump_json(), datetime.now(UTC).isoformat()),
            )
            batch.id = cursor.lastrowid or 0
            connection.execute(
                "UPDATE case_review_batches SET payload_json = ? WHERE id = ?",
                (batch.model_dump_json(), batch.id),
            )
        return batch

    def save(self, batch: CaseReviewBatch, event_type: str) -> CaseReviewBatch:
        with self.connect() as connection:
            connection.execute(
                "UPDATE case_review_batches SET payload_json = ? WHERE id = ? AND project_id = ?",
                (batch.model_dump_json(), batch.id, batch.project_id),
            )
            connection.execute(
                "INSERT INTO case_review_history(batch_id, event_type, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (batch.id, event_type, batch.model_dump_json(), datetime.now(UTC).isoformat()),
            )
        return batch

    def get(self, project_id: int, batch_id: int) -> CaseReviewBatch | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM case_review_batches WHERE id = ? AND project_id = ?",
                (batch_id, project_id),
            ).fetchone()
        return CaseReviewBatch.model_validate_json(row["payload_json"]) if row else None

    def latest_for_generation(self, project_id: int, generation_id: int) -> CaseReviewBatch | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM case_review_batches WHERE project_id = ? AND generation_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (project_id, generation_id),
            ).fetchone()
        return CaseReviewBatch.model_validate_json(row["payload_json"]) if row else None

    def history(self, project_id: int, batch_id: int) -> list[dict] | None:
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT id FROM case_review_batches WHERE id = ? AND project_id = ?", (batch_id, project_id)
            ).fetchone()
            if exists is None:
                return None
            rows = connection.execute(
                "SELECT event_type, payload_json, created_at FROM case_review_history "
                "WHERE batch_id = ? ORDER BY id",
                (batch_id,),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
