import base64
import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.asset_schemas import AssetProvenanceInput, AssetProvenanceRecord, Boundary


class AssetRepository:
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

    def create(self, project_id: int, asset_input: AssetProvenanceInput) -> AssetProvenanceRecord:
        now = self._now()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO assets(project_id, created_at) VALUES (?, ?)",
                (project_id, now),
            )
            asset_id = cursor.lastrowid
            assert asset_id is not None
            self._insert_revision(connection, asset_id, 1, asset_input, now)
        record = self.get(project_id, asset_id)
        assert record is not None
        return record

    def revise(
        self,
        project_id: int,
        asset_id: int,
        asset_input: AssetProvenanceInput,
    ) -> AssetProvenanceRecord | None:
        with self.connect() as connection:
            asset = connection.execute(
                "SELECT id FROM assets WHERE id = ? AND project_id = ?",
                (asset_id, project_id),
            ).fetchone()
            if asset is None:
                return None
            latest = connection.execute(
                "SELECT MAX(revision) AS revision FROM asset_provenance_revisions WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            self._insert_revision(connection, asset_id, latest["revision"] + 1, asset_input, self._now())
        return self.get(project_id, asset_id)

    def get(self, project_id: int, asset_id: int) -> AssetProvenanceRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT revisions.*, assets.project_id
                FROM asset_provenance_revisions AS revisions
                JOIN assets ON assets.id = revisions.asset_id
                WHERE assets.id = ? AND assets.project_id = ?
                ORDER BY revisions.revision DESC LIMIT 1
                """,
                (asset_id, project_id),
            ).fetchone()
        return self._to_record(row) if row else None

    def history(self, project_id: int, asset_id: int) -> list[AssetProvenanceRecord] | None:
        with self.connect() as connection:
            asset = connection.execute(
                "SELECT id FROM assets WHERE id = ? AND project_id = ?",
                (asset_id, project_id),
            ).fetchone()
            if asset is None:
                return None
            rows = connection.execute(
                """
                SELECT revisions.*, assets.project_id
                FROM asset_provenance_revisions AS revisions
                JOIN assets ON assets.id = revisions.asset_id
                WHERE assets.id = ? ORDER BY revisions.revision
                """,
                (asset_id,),
            ).fetchall()
        return [self._to_record(row) for row in rows]

    def list_assets(self, project_id: int) -> list[AssetProvenanceRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT revisions.*, assets.project_id
                FROM assets
                JOIN asset_provenance_revisions AS revisions ON revisions.asset_id = assets.id
                WHERE assets.project_id = ? AND revisions.revision = (
                    SELECT MAX(latest.revision) FROM asset_provenance_revisions AS latest
                    WHERE latest.asset_id = assets.id
                )
                ORDER BY assets.id
                """,
                (project_id,),
            ).fetchall()
        return [self._to_record(row) for row in rows]

    def model_context_assets(self, project_id: int) -> list[AssetProvenanceRecord]:
        return [record for record in self.list_assets(project_id) if record.can_enter_model_context]

    @staticmethod
    def hash_content(content_base64: str) -> str:
        return hashlib.sha256(base64.b64decode(content_base64, validate=True)).hexdigest()

    def _insert_revision(
        self,
        connection: sqlite3.Connection,
        asset_id: int,
        revision: int,
        asset_input: AssetProvenanceInput,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO asset_provenance_revisions(
                asset_id, revision, name, asset_type, provenance_kind, source, usage_permission,
                model_permission, requirement_version, purpose, sha256, change_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                revision,
                asset_input.name,
                asset_input.asset_type,
                asset_input.provenance_kind,
                asset_input.source,
                asset_input.usage_permission,
                asset_input.model_permission,
                asset_input.requirement_version,
                asset_input.purpose,
                self.hash_content(asset_input.content_base64),
                asset_input.change_reason,
                created_at,
            ),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _to_record(row: sqlite3.Row) -> AssetProvenanceRecord:
        boundary, can_enter_requirement_package, can_enter_model_context, reason = classify_boundary(row)
        return AssetProvenanceRecord(
            id=row["asset_id"],
            project_id=row["project_id"],
            revision=row["revision"],
            name=row["name"],
            asset_type=row["asset_type"],
            provenance_kind=row["provenance_kind"],
            source=row["source"],
            usage_permission=row["usage_permission"],
            model_permission=row["model_permission"],
            requirement_version=row["requirement_version"],
            purpose=row["purpose"],
            sha256=row["sha256"],
            change_reason=row["change_reason"],
            created_at=row["created_at"],
            boundary=boundary,
            can_enter_requirement_package=can_enter_requirement_package,
            can_enter_model_context=can_enter_model_context,
            reason=reason,
        )


def classify_boundary(row: sqlite3.Row) -> tuple[Boundary, bool, bool, str]:
    if row["provenance_kind"] == "prohibited" or row["usage_permission"] == "prohibited":
        return "prohibited", False, False, "资产被明确标记为禁止使用"
    if not row["source"] or row["usage_permission"] == "unknown":
        return "unknown", False, False, "缺少来源或明确使用权限，属于来源不明资产"
    expected_permission = {
        "original_synthetic": "project_owned",
        "public_authorized": "public_license",
    }[row["provenance_kind"]]
    if row["usage_permission"] != expected_permission:
        return "unknown", False, False, "来源边界与使用权限不一致，属于来源不明资产"
    can_enter_requirement_package = row["asset_type"] == "requirement_material"
    if row["asset_type"] == "evaluation_truth":
        return row["provenance_kind"], False, False, "评估真值必须与普通模型上下文隔离"
    can_enter_model_context = row["model_permission"] == "allowed"
    if row["provenance_kind"] == "public_authorized":
        reason = "公开授权资产已登记，允许按登记用途和模型权限使用"
        if not can_enter_model_context:
            reason = "公开授权资产可用于登记用途，但未获模型使用权限"
        return "public_authorized", can_enter_requirement_package, can_enter_model_context, reason
    reason = "原创合成资产已登记，允许按登记用途使用"
    if not can_enter_model_context:
        reason = "原创合成资产可用于登记用途，但未获模型使用权限"
    return "original_synthetic", can_enter_requirement_package, can_enter_model_context, reason
