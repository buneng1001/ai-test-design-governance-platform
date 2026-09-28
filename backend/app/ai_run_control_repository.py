"""可恢复 AI 批处理的持久化控制状态。"""

import json
import hashlib
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Iterator


class InputFingerprintMismatchError(Exception):
    pass


class ConcurrentRunResumeError(Exception):
    pass


class BatchAlreadyClaimedError(Exception):
    pass


@dataclass(frozen=True)
class AIRunControl:
    id: str
    project_id: int
    workflow: str
    input_fingerprint: str
    status: str
    next_batch: int
    batch_total: int
    completed_count: int
    payload: dict
    final_asset_type: str | None
    final_asset_id: int | None


@dataclass(frozen=True)
class BatchClaim:
    batch_number: int
    lease_id: str


class AIRunControlRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def recover_after_restart(self) -> None:
        """仅在应用启动时释放遗留领取；普通仓储实例不能抢占其他进程的租约。"""
        with self.connect() as connection:
            connection.execute("UPDATE ai_run_controls SET active_batch_number = NULL, active_lease_id = NULL WHERE active_lease_id IS NOT NULL")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def create(self, project_id: int, workflow: str, payload: dict, batch_total: int) -> AIRunControl:
        run_id = str(uuid.uuid4())
        input_fingerprint = self.fingerprint(payload)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO ai_run_controls(id, project_id, workflow, input_fingerprint, payload_json, status, next_batch, batch_total, completed_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'running', 1, ?, 0, ?, ?)",
                (run_id, project_id, workflow, input_fingerprint, json.dumps(payload, sort_keys=True), batch_total, self._now(), self._now()),
            )
        return self.require(run_id)

    def get(self, run_id: str) -> AIRunControl | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM ai_run_controls WHERE id = ?", (run_id,)).fetchone()
        return self._to_control(row) if row else None

    def require(self, run_id: str) -> AIRunControl:
        run = self.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def request_stop(self, run_id: str) -> AIRunControl:
        with self.connect() as connection:
            connection.execute("UPDATE ai_run_controls SET status = 'stopped', updated_at = ? WHERE id = ? AND status = 'running'", (self._now(), run_id))
        return self.require(run_id)

    def claim_resume(self, run_id: str, input_fingerprint: str) -> AIRunControl:
        run = self.require(run_id)
        if run.input_fingerprint != input_fingerprint:
            raise InputFingerprintMismatchError(run_id)
        if run.status == "completed":
            return run
        with self.connect() as connection:
            changed = connection.execute("UPDATE ai_run_controls SET status = 'running', updated_at = ? WHERE id = ? AND status = 'stopped'", (self._now(), run_id)).rowcount
        if changed == 0:
            raise ConcurrentRunResumeError(run_id)
        return self.require(run_id)

    def claim_next_batch(self, run_id: str) -> BatchClaim:
        run = self.require(run_id)
        if run.status != "running":
            raise BatchAlreadyClaimedError(run_id)
        lease_id = str(uuid.uuid4())
        with self.connect() as connection:
            changed = connection.execute(
                "UPDATE ai_run_controls SET active_batch_number = next_batch, active_lease_id = ?, updated_at = ? "
                "WHERE id = ? AND status = 'running' AND active_lease_id IS NULL AND next_batch <= batch_total",
                (lease_id, self._now(), run_id),
            ).rowcount
            if changed:
                row = connection.execute("SELECT active_batch_number FROM ai_run_controls WHERE id = ?", (run_id,)).fetchone()
                return BatchClaim(batch_number=row["active_batch_number"], lease_id=lease_id)
        raise BatchAlreadyClaimedError(run_id)

    def release_batch_claim(self, run_id: str, lease_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE ai_run_controls SET active_batch_number = NULL, active_lease_id = NULL, updated_at = ? "
                "WHERE id = ? AND active_lease_id = ?", (self._now(), run_id, lease_id),
            )

    def record_validated_batch(self, run_id: str, batch_number: int, output: dict, ai_run_id: int, lease_id: str | None = None) -> AIRunControl:
        with self.connect() as connection:
            if lease_id:
                active = connection.execute(
                    "SELECT active_lease_id FROM ai_run_controls WHERE id = ?", (run_id,),
                ).fetchone()
                if active is None or active["active_lease_id"] != lease_id:
                    raise BatchAlreadyClaimedError(run_id)
            connection.execute("INSERT OR IGNORE INTO ai_run_batch_results(run_id, batch_number, output_json, ai_run_id, created_at) VALUES (?, ?, ?, ?, ?)", (run_id, batch_number, json.dumps(output), ai_run_id, self._now()))
            lease_clause = "AND active_lease_id = ?" if lease_id else ""
            changed = connection.execute(
                "UPDATE ai_run_controls SET completed_count = (SELECT COUNT(*) FROM ai_run_batch_results WHERE run_id = ?), "
                "next_batch = MAX(next_batch, ?), active_batch_number = NULL, active_lease_id = NULL, updated_at = ? "
                f"WHERE id = ? {lease_clause}",
                (run_id, batch_number + 1, self._now(), run_id, *([lease_id] if lease_id else [])),
            ).rowcount
            if lease_id and changed == 0:
                raise BatchAlreadyClaimedError(run_id)
        return self.require(run_id)

    def batch_results(self, run_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT batch_number, output_json, ai_run_id FROM ai_run_batch_results WHERE run_id = ? ORDER BY batch_number", (run_id,)).fetchall()
        return [{"batch_number": row["batch_number"], "output": json.loads(row["output_json"]), "ai_run_id": row["ai_run_id"]} for row in rows]

    def complete(self, run_id: str) -> AIRunControl:
        with self.connect() as connection:
            connection.execute("UPDATE ai_run_controls SET status = 'completed', updated_at = ? WHERE id = ?", (self._now(), run_id))
        return self.require(run_id)

    def record_final_asset(self, run_id: str, asset_type: str, asset_id: int) -> AIRunControl:
        with self.connect() as connection:
            connection.execute("UPDATE ai_run_controls SET final_asset_type = ?, final_asset_id = ?, updated_at = ? WHERE id = ? AND final_asset_id IS NULL", (asset_type, asset_id, self._now(), run_id))
        return self.require(run_id)

    @staticmethod
    def fingerprint(payload: dict) -> str:
        return "v1:" + hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _to_control(row: sqlite3.Row) -> AIRunControl:
        values = {key: row[key] for key in AIRunControl.__dataclass_fields__ if key not in {"payload"}}
        values["payload"] = json.loads(row["payload_json"])
        return AIRunControl(**values)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
