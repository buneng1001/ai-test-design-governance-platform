import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.evaluation_schemas import EvaluationRun


class EvaluationRepository:
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

    def create(self, evaluation: EvaluationRun) -> EvaluationRun:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO ai_evaluation_runs(project_id, truth_asset_id, truth_sha256, ai_run_ids_json, "
                "payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    evaluation.project_id, evaluation.truth_asset_id, evaluation.truth_sha256,
                    json.dumps(evaluation.ai_run_ids), evaluation.model_dump_json(),
                    evaluation.created_at.isoformat(),
                ),
            )
            evaluation.id = cursor.lastrowid or 0
            connection.execute(
                "UPDATE ai_evaluation_runs SET payload_json = ? WHERE id = ?",
                (evaluation.model_dump_json(), evaluation.id),
            )
        return evaluation

    def list(self, project_id: int) -> list[EvaluationRun]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM ai_evaluation_runs WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
        return [EvaluationRun.model_validate_json(row["payload_json"]) for row in rows]

    def latest(self, project_id: int) -> EvaluationRun | None:
        evaluations = self.list(project_id)
        return evaluations[-1] if evaluations else None
