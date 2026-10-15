import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.v020_contracts import normalize_analysis_row
from app.v020_run_repository import active_completed_run_record


class V020Repository:
    """v0.2 正式工作台的页面级持久化，不在浏览器保存业务状态。"""

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

    def save_workspace(
        self,
        project_id: int,
        *,
        supplemental_notes: str | None = None,
        active_requirement_version_id: int | None = None,
        template_mode: str | None = None,
        template_mapping_id: int | None = None,
    ) -> None:
        current = self.workspace_row(project_id)
        values = {
            "supplemental_notes": supplemental_notes if supplemental_notes is not None else current["supplemental_notes"],
            "active_requirement_version_id": active_requirement_version_id
            if active_requirement_version_id is not None else current["active_requirement_version_id"],
            "template_mode": template_mode if template_mode is not None else current["template_mode"],
            "template_mapping_id": template_mapping_id
            if template_mapping_id is not None else current["template_mapping_id"],
        }
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO v020_workspaces(
                    project_id, supplemental_notes, active_requirement_version_id,
                    template_mode, template_mapping_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    supplemental_notes=excluded.supplemental_notes,
                    active_requirement_version_id=excluded.active_requirement_version_id,
                    template_mode=excluded.template_mode,
                    template_mapping_id=excluded.template_mapping_id,
                    updated_at=excluded.updated_at""",
                (
                    project_id, values["supplemental_notes"], values["active_requirement_version_id"],
                    values["template_mode"], values["template_mapping_id"], self.now(),
                ),
            )
            if (active_requirement_version_id is not None
                    and active_requirement_version_id != current["active_requirement_version_id"]):
                for page in ("analysis", "suggestions", "review", "cases"):
                    connection.execute(
                        "INSERT INTO v020_active_results(project_id, page, run_id, updated_at) VALUES (?, ?, NULL, ?) "
                        "ON CONFLICT(project_id, page) DO UPDATE SET run_id=NULL, updated_at=excluded.updated_at",
                        (project_id, page, self.now()),
                    )

    def workspace_row(self, project_id: int) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM v020_workspaces WHERE project_id = ?", (project_id,)
            ).fetchone()
        if row:
            return dict(row)
        return {
            "project_id": project_id,
            "supplemental_notes": "",
            "active_requirement_version_id": None,
            "template_mode": "default",
            "template_mapping_id": None,
            "updated_at": self.now(),
        }

    def save_template(self, project_id: int, mode: str, mapping_id: int | None) -> None:
        current = self.workspace_row(project_id)
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO v020_workspaces(
                    project_id, supplemental_notes, active_requirement_version_id,
                    template_mode, template_mapping_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET template_mode=excluded.template_mode,
                    template_mapping_id=excluded.template_mapping_id, updated_at=excluded.updated_at""",
                (project_id, current["supplemental_notes"], current["active_requirement_version_id"],
                 mode, mapping_id, self.now()),
            )

    def list_project_summaries(self, archived: bool) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT p.*,
                    w.active_requirement_version_id,
                    (SELECT status FROM v020_runs r WHERE r.project_id=p.id AND r.page='analysis'
                        ORDER BY r.created_at DESC LIMIT 1) AS analysis_status,
                    (SELECT status FROM v020_runs r WHERE r.project_id=p.id AND r.page='cases'
                        ORDER BY r.created_at DESC LIMIT 1) AS case_status,
                    (SELECT MAX(created_at) FROM v020_exports e WHERE e.project_id=p.id) AS latest_export_at
                FROM projects p LEFT JOIN v020_workspaces w ON w.project_id=p.id
                WHERE (p.archived_at IS NOT NULL) = ?
                ORDER BY p.updated_at DESC, p.id DESC""",
                (int(archived),),
            ).fetchall()
        return [{
            "id": row["id"], "name": row["name"], "test_object": row["test_object"],
            "software_version": row["software_version"], "updated_at": row["updated_at"],
            "archived_at": row["archived_at"],
            "current_requirement_version": row["active_requirement_version_id"],
            "latest_analysis_status": self.status_label(row["analysis_status"], "尚未执行"),
            "latest_case_status": self.status_label(row["case_status"], "尚未生成"),
            "latest_export_at": row["latest_export_at"],
        } for row in rows]

    def list_payloads(self, table: str, project_id: int, run_id: str | None = None) -> list[dict]:
        allowed = {
            "v020_runs", "v020_analysis_rows", "v020_suggestions", "v020_review_suggestions", "v020_cases",
        }
        if table not in allowed:
            raise ValueError("不支持读取的工作台数据表")
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM {table} WHERE project_id = ? ORDER BY created_at", (project_id,)
            ).fetchall()
        payloads = [json.loads(row["payload_json"]) for row in rows]
        run_key = "id" if table == "v020_runs" else "run_id"
        result = [item for item in payloads if run_id is None or item.get(run_key) == run_id]
        if table == "v020_analysis_rows":
            return [normalize_analysis_row(item, index) for index, item in enumerate(result, start=1)]
        return result

    def active_payloads(self, table: str, project_id: int, page: str) -> list[dict]:
        run_id = self._latest_run_id(project_id, page)
        if run_id is None:
            return []
        active = self.list_payloads(table, project_id, run_id)
        if table != "v020_analysis_rows":
            return active
        derived = [
            item for item in self.list_payloads(table, project_id)
            if item.get("origin") in {"suggestion", "review"}
            and item.get("source_analysis_run_id") == run_id
        ]
        return [normalize_analysis_row(item, index) for index, item in enumerate([*active, *derived], start=1)]

    def active_run_ids(self, project_id: int) -> dict[str, str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT page, run_id FROM v020_active_results WHERE project_id=?", (project_id,),
            ).fetchall()
        return {row["page"]: row["run_id"] for row in rows if row["run_id"] is not None}

    def latest_completed_run(self, project_id: int, page: str) -> dict | None:
        run_id = self._latest_run_id(project_id, page)
        if run_id is None:
            return None
        return next((item for item in self.list_payloads("v020_runs", project_id, run_id)
                     if item.get("id") == run_id), None)

    def active_case_generations(self, project_id: int) -> list[dict]:
        generations = self.case_generations(project_id)
        run_id = self._latest_run_id(project_id, "cases")
        return [item for item in generations if item["run_id"] == run_id]

    def _latest_run_id(self, project_id: int, page: str) -> str | None:
        with self.connect() as connection:
            row = active_completed_run_record(connection, project_id, page)
        return row["id"] if row else None

    def case_generations(self, project_id: int) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM v020_case_generations WHERE project_id=? ORDER BY created_at, rowid",
                (project_id,),
            ).fetchall()
        return [{
            "id": row["id"], "project_id": row["project_id"], "run_id": row["run_id"],
            "scope_ids": json.loads(row["scope_ids_json"]), "template": json.loads(row["template_json"]),
            "supplemental_requirements": row["supplemental_requirements"], "created_at": row["created_at"],
        } for row in rows]

    def export_history(self, project_id: int) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM v020_exports WHERE project_id = ? ORDER BY created_at", (project_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def record_export(self, project_id: int, page: str, format_name: str, filename: str,
                      record_id: str | None = None) -> dict:
        now = self.now()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO v020_exports(project_id, page, format, filename, record_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, page, format_name, filename, record_id, now),
            )
        return {"id": cursor.lastrowid, "project_id": project_id, "page": page,
                "format": format_name, "filename": filename, "record_id": record_id, "created_at": now}

    @staticmethod
    def status_label(status: str | None, empty: str) -> str:
        return {
            "pending": "尚未执行", "running": "正在执行", "completed": "已完成", "failed": "失败",
        }.get(status or "", empty)

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()
