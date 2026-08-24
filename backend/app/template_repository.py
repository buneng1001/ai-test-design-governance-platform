import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.template_schemas import TemplateMappingVersion


class TemplateMappingRepository:
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

    def create(self, mapping: TemplateMappingVersion, content_base64: str) -> TemplateMappingVersion:
        payload = mapping.model_dump(mode="json") | {"content_base64": content_base64}
        with self.connect() as connection:
            version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM template_mappings WHERE project_id = ?",
                (mapping.project_id,),
            ).fetchone()[0]
            mapping.version = version
            payload["version"] = version
            cursor = connection.execute(
                "INSERT INTO template_mappings(project_id, version, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (mapping.project_id, version, json.dumps(payload, ensure_ascii=False), self._now()),
            )
            mapping.id = cursor.lastrowid or 0
            payload["id"] = mapping.id
            connection.execute(
                "UPDATE template_mappings SET payload_json = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), mapping.id),
            )
            self._history(connection, mapping.id, "template_uploaded", payload)
        return mapping

    def get(self, project_id: int, mapping_id: int) -> TemplateMappingVersion | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM template_mappings WHERE project_id = ? AND id = ?",
                (project_id, mapping_id),
            ).fetchone()
        return self._model(row) if row else None

    def list_versions(self, project_id: int) -> list[TemplateMappingVersion]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM template_mappings WHERE project_id = ? ORDER BY version DESC",
                (project_id,),
            ).fetchall()
        return [self._model(row) for row in rows]

    def raw(self, project_id: int, mapping_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM template_mappings WHERE project_id = ? AND id = ?",
                (project_id, mapping_id),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def confirm(self, mapping: TemplateMappingVersion, content_base64: str) -> TemplateMappingVersion:
        mapping.status = "confirmed"
        mapping.confirmed_at = datetime.now(UTC)
        payload = mapping.model_dump(mode="json") | {"content_base64": content_base64}
        with self.connect() as connection:
            connection.execute(
                "UPDATE template_mappings SET payload_json = ? WHERE project_id = ? AND id = ?",
                (json.dumps(payload, ensure_ascii=False), mapping.project_id, mapping.id),
            )
            self._history(connection, mapping.id, "template_mapping_confirmed", payload)
        return mapping

    def history(self, project_id: int, mapping_id: int) -> list[dict] | None:
        if self.get(project_id, mapping_id) is None:
            return None
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT event_type, payload_json, created_at FROM template_mapping_history "
                "WHERE mapping_id = ? ORDER BY id",
                (mapping_id,),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"], "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _model(row: sqlite3.Row) -> TemplateMappingVersion:
        payload = json.loads(row["payload_json"])
        payload.pop("content_base64", None)
        return TemplateMappingVersion.model_validate(payload)

    @staticmethod
    def _history(connection: sqlite3.Connection, mapping_id: int, event: str, payload: dict) -> None:
        connection.execute(
            "INSERT INTO template_mapping_history(mapping_id, event_type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (mapping_id, event, json.dumps(payload, ensure_ascii=False), datetime.now(UTC).isoformat()),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
