import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.ai_schemas import AIAttempt, AIDispositionInput, AIRun, AIModelConfig


class AIRunRepository:
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

    def create_run(self, run: AIRun) -> AIRun:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ai_runs(
                    project_id, task_type, model_config_json, prompt_version, input_asset_versions_json,
                    output_json, validation_status, validation_errors_json, status, is_mock, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.project_id, run.task_type, run.model_parameters.model_dump_json(), run.prompt_version,
                    json.dumps(run.input_asset_versions), json.dumps(run.output), run.validation_status,
                    json.dumps(run.validation_errors), run.status, run.is_mock, run.created_at.isoformat(),
                ),
            )
            run_id = cursor.lastrowid
            assert run_id is not None
            for attempt in run.attempts:
                self._insert_attempt(connection, run_id, attempt)
        return self.get(run.project_id, run_id)

    def add_disposition(self, project_id: int, run_id: int, disposition: AIDispositionInput) -> AIRun | None:
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT id FROM ai_runs WHERE id = ? AND project_id = ?", (run_id, project_id)
            ).fetchone()
            if exists is None:
                return None
            connection.execute(
                "INSERT INTO ai_run_dispositions(run_id, decision, reason, created_at) VALUES (?, ?, ?, ?)",
                (run_id, disposition.decision, disposition.reason, self._now()),
            )
        return self.get(project_id, run_id)

    def get(self, project_id: int, run_id: int) -> AIRun | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_runs WHERE id = ? AND project_id = ?", (run_id, project_id)
            ).fetchone()
            if row is None:
                return None
            return self._to_run(connection, row)

    def list(self, project_id: int) -> list[AIRun]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ai_runs WHERE project_id = ? ORDER BY id", (project_id,)
            ).fetchall()
            return [self._to_run(connection, row) for row in rows]

    def _to_run(self, connection: sqlite3.Connection, row: sqlite3.Row) -> AIRun:
        attempts = connection.execute(
            "SELECT * FROM ai_run_attempts WHERE run_id = ? ORDER BY attempt", (row["id"],)
        ).fetchall()
        disposition = connection.execute(
            "SELECT decision, reason, created_at FROM ai_run_dispositions WHERE run_id = ? ORDER BY id DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        dispositions = connection.execute(
            "SELECT decision, reason, created_at FROM ai_run_dispositions WHERE run_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall()
        return AIRun(
            id=row["id"], project_id=row["project_id"], task_type=row["task_type"],
            model_parameters=AIModelConfig.model_validate_json(row["model_config_json"]),
            prompt_version=row["prompt_version"], input_asset_versions=json.loads(row["input_asset_versions_json"]),
            output=json.loads(row["output_json"]) if row["output_json"] else None,
            validation_status=row["validation_status"], validation_errors=json.loads(row["validation_errors_json"]),
            status=row["status"], is_mock=bool(row["is_mock"]), created_at=row["created_at"],
            attempts=[AIAttempt.model_validate(dict(item)) for item in attempts],
            dispositions=[dict(item) for item in dispositions],
            disposition=dict(disposition) if disposition else None,
        )

    @staticmethod
    def _insert_attempt(connection: sqlite3.Connection, run_id: int, attempt: AIAttempt) -> None:
        connection.execute(
            "INSERT INTO ai_run_attempts(run_id, attempt, started_at, elapsed_ms, status, error_code, retryable) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, attempt.attempt, attempt.started_at.isoformat(), attempt.elapsed_ms, attempt.status,
             attempt.error_code, attempt.retryable),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
