import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.requirement_schemas import RequirementPackage, RequirementVersion


class RequirementRepository:
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

    def create_package(self, package: RequirementPackage) -> RequirementPackage:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO requirement_packages(project_id, name, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (package.project_id, package.name, package.model_dump_json(), package.created_at.isoformat()),
            )
            package_id = cursor.lastrowid
            assert package_id is not None
            package.id = package_id
            connection.execute(
                "UPDATE requirement_packages SET payload_json = ? WHERE id = ?",
                (package.model_dump_json(), package_id),
            )
        return package

    def get_package(self, project_id: int, package_id: int) -> RequirementPackage | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json, published_version_id FROM requirement_packages WHERE id = ? AND project_id = ?",
                (package_id, project_id),
            ).fetchone()
        if row is None:
            return None
        package = RequirementPackage.model_validate_json(row["payload_json"])
        if row["published_version_id"] is not None:
            package.status = "published"
            package.published_version_id = row["published_version_id"]
        return package

    def publish(self, package: RequirementPackage) -> RequirementVersion | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT published_version_id FROM requirement_packages WHERE id = ? AND project_id = ?",
                (package.id, package.project_id),
            ).fetchone()
            if row is None or row["published_version_id"] is not None:
                return None
            next_version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM requirement_versions WHERE project_id = ?",
                (package.project_id,),
            ).fetchone()["version"]
            now = self._now()
            version = RequirementVersion(
                id=0,
                project_id=package.project_id,
                package_id=package.id,
                version=next_version,
                name=package.name,
                materials=package.materials,
                diagnostics=package.diagnostics,
                created_at=now,
            )
            cursor = connection.execute(
                """
                INSERT INTO requirement_versions(project_id, package_id, version, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (package.project_id, package.id, next_version, version.model_dump_json(), now),
            )
            version.id = cursor.lastrowid
            connection.execute(
                "UPDATE requirement_versions SET payload_json = ? WHERE id = ?",
                (version.model_dump_json(), version.id),
            )
            connection.execute(
                "UPDATE requirement_packages SET published_version_id = ? WHERE id = ?",
                (version.id, package.id),
            )
        return version

    def list_versions(self, project_id: int) -> list[RequirementVersion]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM requirement_versions WHERE project_id = ? ORDER BY version",
                (project_id,),
            ).fetchall()
        return [RequirementVersion.model_validate(json.loads(row["payload_json"])) for row in rows]

    def get_version(self, project_id: int, version_id: int) -> RequirementVersion | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM requirement_versions WHERE id = ? AND project_id = ?",
                (version_id, project_id),
            ).fetchone()
        return RequirementVersion.model_validate_json(row["payload_json"]) if row else None

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
