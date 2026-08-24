import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.case_schemas import CaseGeneration


class CaseGenerationRepository:
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

    def create(self, generation: CaseGeneration) -> CaseGeneration:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO case_generations(project_id, design_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    generation.project_id, generation.design_id, generation.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            generation.id = cursor.lastrowid or 0
            for candidate in generation.candidates:
                candidate.generation_id = generation.id
            connection.execute(
                "UPDATE case_generations SET payload_json = ? WHERE id = ?",
                (generation.model_dump_json(), generation.id),
            )
        return generation

    def get(self, project_id: int, generation_id: int) -> CaseGeneration | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM case_generations WHERE project_id = ? AND id = ?",
                (project_id, generation_id),
            ).fetchone()
        return CaseGeneration.model_validate_json(row["payload_json"]) if row else None

    def list(self, project_id: int) -> list[CaseGeneration]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM case_generations WHERE project_id = ? ORDER BY id DESC", (project_id,)
            ).fetchall()
        return [CaseGeneration.model_validate_json(row["payload_json"]) for row in rows]
