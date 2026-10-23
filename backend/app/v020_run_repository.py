import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.v020_contracts import normalize_analysis_row


def active_completed_run_record(connection: sqlite3.Connection, project_id: int, page: str) -> sqlite3.Row | None:
    marker = connection.execute(
        "SELECT run_id FROM v020_active_results WHERE project_id=? AND page=?", (project_id, page),
    ).fetchone()
    if marker is not None:
        if marker["run_id"] is None:
            return None
        return connection.execute(
            "SELECT id, payload_json FROM v020_runs WHERE project_id=? AND page=? AND id=? AND status='completed'",
            (project_id, page, marker["run_id"]),
        ).fetchone()
    return connection.execute(
        "SELECT id, payload_json FROM v020_runs WHERE project_id=? AND page=? AND status='completed' "
        "ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (project_id, page),
    ).fetchone()


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
            current = connection.execute(
                "SELECT payload_json FROM v020_runs WHERE id=? AND project_id=?",
                (payload["id"], payload["project_id"]),
            ).fetchone()
            if current and json.loads(current["payload_json"]).get("cancel_requested"):
                # 停止请求可能与模型线程同时写运行进度；一旦置位就不能被旧快照覆盖。
                payload["cancel_requested"] = True
            connection.execute(
                "UPDATE v020_runs SET status=?, payload_json=?, updated_at=? WHERE id=? AND project_id=?",
                (payload["status"], self._json(payload), self.now(), payload["id"], payload["project_id"]),
            )
        return payload

    def reusable_run(self, project_id: int, page: str, mode: str, fingerprint: str) -> dict | None:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM v020_runs WHERE project_id=? AND page=? AND mode=? "
                "AND status='completed' ORDER BY created_at DESC, rowid DESC",
                (project_id, page, mode),
            ).fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"])
            if payload.get("input_fingerprint") == fingerprint:
                return payload
        return None

    def resumable_run(self, project_id: int, page: str, mode: str, fingerprint: str) -> dict | None:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM v020_runs WHERE project_id=? AND page=? AND mode=? "
                "AND status IN ('failed', 'stopped') ORDER BY created_at DESC, rowid DESC",
                (project_id, page, mode),
            ).fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"])
            if payload.get("input_fingerprint") == fingerprint and payload.get("checkpoints"):
                return payload
        return None

    def get_run(self, project_id: int, run_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM v020_runs WHERE project_id=? AND id=?", (project_id, run_id),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def request_cancel(self, project_id: int, run_id: str) -> dict | None:
        run = self.get_run(project_id, run_id)
        if run is None:
            return None
        if run.get("status") == "running":
            run["cancel_requested"] = True
            run["next_step"] = "正在停止；已完成的来源范围会保留为检查点。"
            self.update_run(run)
        return run

    def set_active_run(self, project_id: int, page: str, run_id: str) -> None:
        with self.connect() as connection:
            previous = connection.execute(
                "SELECT run_id FROM v020_active_results WHERE project_id=? AND page=?", (project_id, page),
            ).fetchone()
            if page in {"understanding", "analysis"} and (previous is None or previous["run_id"] != run_id):
                downstream_pages = (("analysis", "suggestions", "review", "cases")
                                    if page == "understanding" else ("suggestions", "review", "cases"))
                for downstream_page in downstream_pages:
                    connection.execute(
                        "INSERT INTO v020_active_results(project_id, page, run_id, updated_at) VALUES (?, ?, NULL, ?) "
                        "ON CONFLICT(project_id, page) DO UPDATE SET run_id=NULL, updated_at=excluded.updated_at",
                        (project_id, downstream_page, self.now()),
                    )
            connection.execute(
                "INSERT INTO v020_active_results(project_id, page, run_id, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(project_id, page) DO UPDATE SET run_id=excluded.run_id, updated_at=excluded.updated_at",
                (project_id, page, run_id, self.now()),
            )

    def result_for_run(self, project_id: int, page: str, run: dict) -> dict:
        if page == "understanding":
            return {"understanding": run.get("material_understanding")}
        table = {
            "analysis": "v020_analysis_rows",
            "suggestions": "v020_suggestions",
            "review": "v020_review_suggestions",
            "cases": "v020_cases",
        }[page]
        items = self._payloads_for_run(table, project_id, run["id"])
        if page == "analysis":
            return {"rows": items}
        if page in {"suggestions", "review"}:
            return {"suggestions": items}
        with self.connect() as connection:
            record = connection.execute(
                "SELECT * FROM v020_case_generations WHERE project_id=? AND run_id=?",
                (project_id, run["id"]),
            ).fetchone()
        if record is None:
            return {"generation_id": None, "scope_ids": [], "template": {"sheets": []}, "cases": items}
        return {
            "generation_id": record["id"],
            "scope_ids": json.loads(record["scope_ids_json"]),
            "template": json.loads(record["template_json"]),
            "cases": items,
        }

    def active_analysis_rows(self, project_id: int) -> list[dict]:
        run = self.latest_completed_run(project_id, "analysis")
        base = self._payloads_for_run("v020_analysis_rows", project_id, run["id"]) if run else []
        active_run_id = run["id"] if run else None
        with self.connect() as connection:
            records = connection.execute(
                "SELECT selected, payload_json FROM v020_analysis_rows WHERE project_id=? ORDER BY created_at, rowid",
                (project_id,),
            ).fetchall()
        derived = []
        for record in records:
            payload = json.loads(record["payload_json"])
            if (payload.get("origin") not in {"suggestion", "review"}
                    or payload.get("source_analysis_run_id") != active_run_id):
                continue
            payload["selected"] = bool(record["selected"])
            derived.append(payload)
        return [normalize_analysis_row(row, index) for index, row in enumerate([*base, *derived], start=1)]

    def latest_completed_run(self, project_id: int, page: str) -> dict | None:
        with self.connect() as connection:
            row = active_completed_run_record(connection, project_id, page)
        return json.loads(row["payload_json"]) if row else None

    def _payloads_for_run(self, table: str, project_id: int, run_id: str) -> list[dict]:
        with self.connect() as connection:
            records = connection.execute(
                f"SELECT * FROM {table} WHERE project_id=? ORDER BY created_at, rowid", (project_id,),
            ).fetchall()
        items = []
        for record in records:
            payload = json.loads(record["payload_json"])
            if payload.get("run_id") != run_id:
                continue
            if "selected" in record.keys():
                payload["selected"] = bool(record["selected"])
            if "disposition" in record.keys():
                payload["disposition"] = record["disposition"]
            if "included" in record.keys():
                payload["included"] = bool(record["included"])
                payload["removed"] = bool(record["removed"])
            items.append(payload)
        if table == "v020_analysis_rows":
            return [normalize_analysis_row(item, index) for index, item in enumerate(items, start=1)]
        return items

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
        return [normalize_analysis_row(row, index) for index, row in enumerate(rows, start=1)]

    def equivalent_analysis_row(self, project_id: int, candidate: dict) -> dict | None:
        for row in self.analysis_rows(project_id):
            row_source_run = (row.get("run_id") if row.get("origin") == "analysis"
                              else row.get("source_analysis_run_id"))
            if (
                row_source_run == candidate.get("source_analysis_run_id")
                and row.get("related_requirement_id") == candidate.get("related_requirement_id")
                and row.get("test_item") == candidate.get("test_item")
                and row.get("test_type") == candidate.get("test_type")
            ):
                return row
        return None

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
