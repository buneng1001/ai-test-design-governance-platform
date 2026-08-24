import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.design_schemas import DesignAsset


class DesignRepository:
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

    def create(self, design: DesignAsset, event: str = "design_created") -> DesignAsset:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO test_designs(project_id, requirement_version_id, payload_json) VALUES (?, ?, ?)",
                (design.project_id, design.requirement_version_id, design.model_dump_json()),
            )
            design.id = cursor.lastrowid or 0
            connection.execute(
                "UPDATE test_designs SET payload_json = ? WHERE id = ?",
                (design.model_dump_json(), design.id),
            )
            self._history(connection, design.id, event, design)
        return design

    def get(self, project_id: int, design_id: int) -> DesignAsset | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM test_designs WHERE project_id = ? AND id = ?", (project_id, design_id)
            ).fetchone()
        return DesignAsset.model_validate_json(row["payload_json"]) if row else None

    def latest_for_version(self, project_id: int, version_id: int) -> DesignAsset | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM test_designs WHERE project_id = ? AND requirement_version_id = ? "
                "ORDER BY id DESC LIMIT 1", (project_id, version_id)
            ).fetchone()
        return DesignAsset.model_validate_json(row["payload_json"]) if row else None

    def save(self, design: DesignAsset, event: str) -> DesignAsset:
        with self.connect() as connection:
            connection.execute(
                "UPDATE test_designs SET payload_json = ? WHERE project_id = ? AND id = ?",
                (design.model_dump_json(), design.project_id, design.id),
            )
            self._history(connection, design.id, event, design)
        return design

    def history(self, project_id: int, design_id: int) -> list[dict] | None:
        if self.get(project_id, design_id) is None:
            return None
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT event_type, payload_json, created_at FROM test_design_history "
                "WHERE design_id = ? ORDER BY id", (design_id,)
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _history(connection: sqlite3.Connection, design_id: int, event: str, design: DesignAsset) -> None:
        connection.execute(
            "INSERT INTO test_design_history(design_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (design_id, event, design.model_dump_json(), datetime.now(UTC).isoformat()),
        )
