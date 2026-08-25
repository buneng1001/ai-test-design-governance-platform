import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.change_impact_schemas import ChangeImpactAnalysis, RegressionSelection


class ChangeImpactRepository:
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

    def create_analysis(self, analysis: ChangeImpactAnalysis) -> ChangeImpactAnalysis:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO change_impact_analyses(project_id, base_version_id, target_version_id, payload_json, "
                "created_at) VALUES (?, ?, ?, ?, ?)",
                (analysis.project_id, analysis.base_version_id, analysis.target_version_id,
                 analysis.model_dump_json(), analysis.created_at.isoformat()),
            )
            analysis.id = cursor.lastrowid or 0
            connection.execute("UPDATE change_impact_analyses SET payload_json = ? WHERE id = ?",
                               (analysis.model_dump_json(), analysis.id))
            self._history(connection, analysis.id, "analysis_created", analysis)
        return analysis

    def get_analysis(self, project_id: int, analysis_id: int) -> ChangeImpactAnalysis | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM change_impact_analyses WHERE project_id = ? AND id = ?",
                (project_id, analysis_id),
            ).fetchone()
        return ChangeImpactAnalysis.model_validate_json(row["payload_json"]) if row else None

    def list_analyses(self, project_id: int) -> list[ChangeImpactAnalysis]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM change_impact_analyses WHERE project_id = ? ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        return [ChangeImpactAnalysis.model_validate_json(row["payload_json"]) for row in rows]

    def save_analysis(self, analysis: ChangeImpactAnalysis, event: str) -> ChangeImpactAnalysis:
        with self.connect() as connection:
            connection.execute("UPDATE change_impact_analyses SET payload_json = ? WHERE id = ? AND project_id = ?",
                               (analysis.model_dump_json(), analysis.id, analysis.project_id))
            self._history(connection, analysis.id, event, analysis)
        return analysis

    def create_selection(self, selection: RegressionSelection) -> RegressionSelection:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO regression_selections(project_id, analysis_id, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    selection.project_id, selection.analysis_id, selection.model_dump_json(),
                    selection.created_at.isoformat(),
                ),
            )
            selection.id = cursor.lastrowid or 0
            connection.execute("UPDATE regression_selections SET payload_json = ? WHERE id = ?",
                               (selection.model_dump_json(), selection.id))
        return selection

    def get_selection(self, project_id: int, selection_id: int) -> RegressionSelection | None:
        with self.connect() as connection:
            row = connection.execute("SELECT payload_json FROM regression_selections WHERE project_id = ? AND id = ?",
                                     (project_id, selection_id)).fetchone()
        return RegressionSelection.model_validate_json(row["payload_json"]) if row else None

    def list_selections(self, project_id: int) -> list[RegressionSelection]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM regression_selections WHERE project_id = ? ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        return [RegressionSelection.model_validate_json(row["payload_json"]) for row in rows]

    def save_selection(self, selection: RegressionSelection) -> RegressionSelection:
        with self.connect() as connection:
            connection.execute("UPDATE regression_selections SET payload_json = ? WHERE project_id = ? AND id = ?",
                               (selection.model_dump_json(), selection.project_id, selection.id))
        return selection

    @staticmethod
    def _history(connection: sqlite3.Connection, analysis_id: int, event: str,
                 analysis: ChangeImpactAnalysis) -> None:
        connection.execute(
            "INSERT INTO change_impact_history(analysis_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (analysis_id, event, analysis.model_dump_json(), datetime.now(UTC).isoformat()),
        )
