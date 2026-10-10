import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class V020RunRepository:
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

    def create_run(self, payload: dict) -> dict:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO v020_runs(id, project_id, page, mode, status, payload_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload["id"], payload["project_id"], payload["page"], payload["mode"], payload["status"],
                    self._json(payload), payload["started_at"], payload["started_at"],
                ),
            )
        return payload

    def update_run(self, payload: dict) -> dict:
        with self.connect() as connection:
            connection.execute(
                "UPDATE v020_runs SET status=?, payload_json=?, updated_at=? WHERE id=? AND project_id=?",
                (payload["status"], self._json(payload), self.now(), payload["id"], payload["project_id"]),
            )
        return payload

    def save_analysis_rows(self, project_id: int, run_id: str, rows: list[dict]) -> list[dict]:
        now = self.now()
        with self.connect() as connection:
            for row in rows:
                connection.execute(
                    "INSERT INTO v020_analysis_rows(id, project_id, run_id, selected, payload_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (row["id"], project_id, run_id, int(row.get("selected", False)), self._json(row), now),
                )
        return rows

    def analysis_rows(self, project_id: int, *, selected_only: bool = False) -> list[dict]:
        query = "SELECT selected, payload_json FROM v020_analysis_rows WHERE project_id = ?"
        if selected_only:
            query += " AND selected = 1"
        query += " ORDER BY created_at, rowid"
        with self.connect() as connection:
            records = connection.execute(query, (project_id,)).fetchall()
        rows = []
        for record in records:
            payload = json.loads(record["payload_json"])
            payload["selected"] = bool(record["selected"])
            rows.append(payload)
        return rows

    def set_selection(self, project_id: int, row_ids: list[str], selected: bool) -> int:
        with self.connect() as connection:
            records = connection.execute(
                f"SELECT id, payload_json FROM v020_analysis_rows WHERE project_id=? "
                f"AND id IN ({','.join('?' for _ in row_ids)})",
                (project_id, *row_ids),
            ).fetchall()
            if len(records) != len(set(row_ids)):
                raise ValueError("部分需求分析结果不存在或不属于当前项目")
            for record in records:
                payload = json.loads(record["payload_json"])
                payload["selected"] = selected
                connection.execute(
                    "UPDATE v020_analysis_rows SET selected=?, payload_json=? WHERE id=?",
                    (int(selected), self._json(payload), record["id"]),
                )
            count = connection.execute(
                "SELECT COUNT(*) FROM v020_analysis_rows WHERE project_id=? AND selected=1", (project_id,)
            ).fetchone()[0]
        return count

    def save_items(self, table: str, project_id: int, run_id: str, items: list[dict]) -> list[dict]:
        if table not in {"v020_suggestions", "v020_review_suggestions"}:
            raise ValueError("不支持的建议类型")
        now = self.now()
        with self.connect() as connection:
            for item in items:
                connection.execute(
                    f"INSERT INTO {table}(id, project_id, run_id, disposition, payload_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (item["id"], project_id, run_id, "pending", self._json(item), now, now),
                )
        return items

    def dispose_item(self, table: str, project_id: int, item_id: str, disposition: str) -> dict | None:
        if table not in {"v020_suggestions", "v020_review_suggestions"}:
            raise ValueError("不支持的建议类型")
        with self.connect() as connection:
            record = connection.execute(
                f"SELECT payload_json FROM {table} WHERE project_id=? AND id=?", (project_id, item_id),
            ).fetchone()
            if not record:
                return None
            payload = json.loads(record["payload_json"])
            payload["disposition"] = disposition
            connection.execute(
                f"UPDATE {table} SET disposition=?, payload_json=?, updated_at=? WHERE project_id=? AND id=?",
                (disposition, self._json(payload), self.now(), project_id, item_id),
            )
        return payload

    def create_generation(self, generation: dict, cases: list[dict]) -> tuple[dict, list[dict]]:
        now = self.now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO v020_case_generations(id, project_id, run_id, scope_ids_json, template_json, "
                "supplemental_requirements, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    generation["id"], generation["project_id"], generation["run_id"],
                    self._json(generation["scope_ids"]), self._json(generation["template"]),
                    generation["supplemental_requirements"], now,
                ),
            )
            for case in cases:
                connection.execute(
                    "INSERT INTO v020_cases(id, project_id, generation_id, included, removed, payload_json, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (case["id"], generation["project_id"], generation["id"], 1, 0, self._json(case), now, now),
                )
        return generation, cases

    def update_case(self, project_id: int, case_id: str, updates: dict) -> dict | None:
        with self.connect() as connection:
            record = connection.execute(
                "SELECT included, removed, payload_json FROM v020_cases WHERE project_id=? AND id=?",
                (project_id, case_id),
            ).fetchone()
            if not record:
                return None
            payload = json.loads(record["payload_json"])
            payload.update({key: value for key, value in updates.items() if value is not None})
            included = int(payload.get("included", bool(record["included"])))
            removed = int(payload.get("removed", bool(record["removed"])))
            connection.execute(
                "UPDATE v020_cases SET included=?, removed=?, payload_json=?, updated_at=? WHERE project_id=? AND id=?",
                (included, removed, self._json(payload), self.now(), project_id, case_id),
            )
        return payload

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()
