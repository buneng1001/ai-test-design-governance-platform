import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.review_schemas import RequirementAnalysis


class RequirementReviewRepository:
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

    def create(self, analysis: RequirementAnalysis) -> RequirementAnalysis:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO requirement_analyses(project_id, requirement_version_id, payload_json) VALUES (?, ?, ?)",
                (analysis.project_id, analysis.requirement_version_id, analysis.model_dump_json()),
            )
            analysis.id = cursor.lastrowid or 0
            connection.execute(
                "UPDATE requirement_analyses SET payload_json = ? WHERE id = ?",
                (analysis.model_dump_json(), analysis.id),
            )
            self._record_history(connection, analysis.id, "analysis_created", analysis.model_dump_json())
        return analysis

    def get(self, project_id: int, analysis_id: int) -> RequirementAnalysis | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM requirement_analyses WHERE id = ? AND project_id = ?",
                (analysis_id, project_id),
            ).fetchone()
        return RequirementAnalysis.model_validate_json(row["payload_json"]) if row else None

    def latest_for_version(self, project_id: int, version_id: int) -> RequirementAnalysis | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM requirement_analyses WHERE project_id = ? AND requirement_version_id = "
                "? ORDER BY id DESC LIMIT 1",
                (project_id, version_id),
            ).fetchone()
        return RequirementAnalysis.model_validate_json(row["payload_json"]) if row else None

    def save(self, analysis: RequirementAnalysis, event: str) -> RequirementAnalysis:
        with self.connect() as connection:
            connection.execute(
                "UPDATE requirement_analyses SET payload_json = ? WHERE id = ? AND project_id = ?",
                (analysis.model_dump_json(), analysis.id, analysis.project_id),
            )
            self._record_history(connection, analysis.id, event, analysis.model_dump_json())
        return analysis

    def history(self, project_id: int, analysis_id: int) -> list[dict] | None:
        if self.get(project_id, analysis_id) is None:
            return None
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT event_type, payload_json, created_at FROM requirement_analysis_history "
                "WHERE analysis_id = ? ORDER BY id",
                (analysis_id,),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _record_history(self, connection: sqlite3.Connection, analysis_id: int, event: str, payload: str) -> None:
        connection.execute(
            "INSERT INTO requirement_analysis_history(analysis_id, event_type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (analysis_id, event, payload, datetime.now(UTC).isoformat()),
        )
