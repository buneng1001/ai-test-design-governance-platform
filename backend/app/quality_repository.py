import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.quality_schemas import DefectPatternCandidate, QualityIssueInput, QualityIssueReference


class QualityRepository:
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

    def create_issue(self, project_id: int, data: QualityIssueInput, batch_id: int,
                     stable_case_id: str | None) -> QualityIssueReference:
        now = datetime.now(UTC)
        payload = {**data.model_dump(mode="json"), "batch_id": batch_id, "stable_case_id": stable_case_id}
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO quality_issue_references(project_id, payload_json, created_at) VALUES (?, ?, ?)",
                (project_id, json.dumps(payload, ensure_ascii=False), now.isoformat()),
            )
            issue_id = cursor.lastrowid or 0
        return QualityIssueReference(
            id=issue_id, project_id=project_id, batch_id=batch_id, stable_case_id=stable_case_id,
            created_at=now, **data.model_dump(),
        )

    def list_issues(self, project_id: int) -> list[QualityIssueReference]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, payload_json, created_at FROM quality_issue_references "
                "WHERE project_id = ? ORDER BY id", (project_id,)
            ).fetchall()
        return [self._issue(row, project_id) for row in rows]

    def create_pattern(self, pattern: DefectPatternCandidate) -> DefectPatternCandidate:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO defect_patterns(project_id, payload_json, created_at) VALUES (?, ?, ?)",
                (pattern.project_id, pattern.model_dump_json(), pattern.created_at.isoformat()),
            )
            pattern.id = cursor.lastrowid or 0
            connection.execute(
                "UPDATE defect_patterns SET payload_json = ? WHERE id = ?",
                (pattern.model_dump_json(), pattern.id),
            )
        return pattern

    def get_pattern(self, project_id: int, pattern_id: int) -> DefectPatternCandidate | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM defect_patterns WHERE project_id = ? AND id = ?",
                (project_id, pattern_id),
            ).fetchone()
        return DefectPatternCandidate.model_validate_json(row["payload_json"]) if row else None

    def save_pattern(self, pattern: DefectPatternCandidate) -> DefectPatternCandidate:
        with self.connect() as connection:
            connection.execute(
                "UPDATE defect_patterns SET payload_json = ? WHERE project_id = ? AND id = ?",
                (pattern.model_dump_json(), pattern.project_id, pattern.id),
            )
        return pattern

    @staticmethod
    def _issue(row: sqlite3.Row, project_id: int) -> QualityIssueReference:
        payload = json.loads(row["payload_json"])
        return QualityIssueReference(
            id=row["id"], project_id=project_id, batch_id=payload.pop("batch_id", 0),
            stable_case_id=payload.pop("stable_case_id", None), created_at=row["created_at"], **payload,
        )
