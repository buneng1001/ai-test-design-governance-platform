import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.execution_result_schemas import (
    ExecutionResultInput,
    ExecutionResultRecord,
    ResultConflict,
)


class ExecutionResultRepository:
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

    def find_source(self, batch_id: int, source_type: str, source_record_id: str) -> ExecutionResultRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM execution_result_records WHERE batch_id = ? AND source_type = ? "
                "AND source_record_id = ?",
                (batch_id, source_type, source_record_id),
            ).fetchone()
        return self._to_record(row) if row else None

    def create(
        self,
        project_id: int,
        batch_id: int,
        source_type: str,
        result: ExecutionResultInput,
        match_status: str,
        match_reason: str | None,
        matched_by: str | None,
        stable_case_id: str | None,
        case_revision_id: str | None,
        execution_sequence: int | None,
        retest_of_result_id: int | None,
    ) -> ExecutionResultRecord:
        now = datetime.now(UTC).isoformat()
        payload = result.model_dump(mode="json")
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO execution_result_records(project_id, batch_id, source_type, source_record_id, "
                "payload_json, match_status, stable_case_id, case_revision_id, execution_sequence, "
                "retest_of_result_id, match_reason, matched_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, batch_id, source_type, result.source_record_id, json.dumps(payload, ensure_ascii=False),
                 match_status, stable_case_id, case_revision_id, execution_sequence, retest_of_result_id,
                 match_reason, matched_by, now),
            )
            record_id = cursor.lastrowid or 0
        return ExecutionResultRecord(
            id=record_id, batch_id=batch_id, source_type=source_type, source_record_id=result.source_record_id,
            stable_case_id=stable_case_id, case_revision_id=case_revision_id,
            external_case_number=result.external_case_number, execution_record_id=result.execution_record_id,
            execution_sequence=execution_sequence, status=result.status, actual_result=result.actual_result,
            reason=result.reason, executor=result.executor, executed_at=result.executed_at,
            evidence_references=result.evidence_references, match_status=match_status,
            retest_of_result_id=retest_of_result_id, match_reason=match_reason, matched_by=matched_by, created_at=now,
        )

    def list_records(self, batch_id: int) -> list[ExecutionResultRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM execution_result_records WHERE batch_id = ? ORDER BY id", (batch_id,)
            ).fetchall()
        return [self._to_record(row) for row in rows]

    def update_match(
        self, batch_id: int, record_id: int, status: str, stable_case_id: str | None,
        case_revision_id: str | None, reason: str, matched_by: str,
    ) -> ExecutionResultRecord | None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE execution_result_records SET match_status = ?, stable_case_id = ?, case_revision_id = ?, "
                "match_reason = ?, matched_by = ? WHERE id = ? AND batch_id = ?",
                (status, stable_case_id, case_revision_id, reason, matched_by, record_id, batch_id),
            )
            row = connection.execute(
                "SELECT * FROM execution_result_records WHERE id = ? AND batch_id = ?", (record_id, batch_id)
            ).fetchone()
        if row is None:
            return None
        record = self._to_record(row)
        return record

    def create_conflict(
        self, project_id: int, batch_id: int, result_ids: list[int], statuses: dict[str, str]
    ) -> ResultConflict:
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO execution_result_conflicts(project_id, batch_id, result_ids_json, payload_json, status, "
                "created_at) VALUES (?, ?, ?, ?, 'open', ?)",
                (project_id, batch_id, json.dumps(result_ids), json.dumps({"statuses": statuses}), now),
            )
            conflict_id = cursor.lastrowid or 0
        return ResultConflict(
            id=conflict_id, batch_id=batch_id, result_ids=result_ids, statuses=statuses, status="open"
        )

    def list_conflicts(self, batch_id: int) -> list[ResultConflict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM execution_result_conflicts WHERE batch_id = ? ORDER BY id", (batch_id,)
            ).fetchall()
        return [self._to_conflict(row) for row in rows]

    def resolve_conflict(
        self, conflict_id: int, decision: str, rationale: str, confirmer_name: str
    ) -> ResultConflict | None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE execution_result_conflicts SET status = 'resolved', payload_json = ?, resolved_at = ? "
                "WHERE id = ? AND status = 'open'",
                (json.dumps({"decision": decision, "rationale": rationale, "confirmed_by": confirmer_name},
                            ensure_ascii=False), datetime.now(UTC).isoformat(), conflict_id),
            )
            row = connection.execute("SELECT * FROM execution_result_conflicts WHERE id = ?", (conflict_id,)).fetchone()
        return self._to_conflict(row) if row else None

    def save_conclusion(self, batch_id: int, conclusion: dict[str, str]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO execution_batch_conclusions(batch_id, payload_json, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(batch_id) DO UPDATE SET payload_json = excluded.payload_json, "
                "created_at = excluded.created_at",
                (batch_id, json.dumps(conclusion, ensure_ascii=False), datetime.now(UTC).isoformat()),
            )

    def get_conclusion(self, batch_id: int) -> dict[str, str] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM execution_batch_conclusions WHERE batch_id = ?", (batch_id,)
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    @staticmethod
    def _to_record(row: sqlite3.Row) -> ExecutionResultRecord:
        payload = json.loads(row["payload_json"])
        return ExecutionResultRecord(
            id=row["id"], batch_id=row["batch_id"], source_type=row["source_type"],
            source_record_id=row["source_record_id"], stable_case_id=row["stable_case_id"],
            case_revision_id=row["case_revision_id"], external_case_number=payload.get("external_case_number"),
            execution_record_id=payload.get("execution_record_id"), status=payload["status"],
            actual_result=payload.get("actual_result", ""), reason=payload.get("reason", ""),
            executor=payload.get("executor", ""), executed_at=payload.get("executed_at"),
            evidence_references=payload.get("evidence_references", []), execution_sequence=row["execution_sequence"],
            match_status=row["match_status"], match_reason=row["match_reason"], matched_by=row["matched_by"],
            retest_of_result_id=row["retest_of_result_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _to_conflict(row: sqlite3.Row) -> ResultConflict:
        payload = json.loads(row["payload_json"])
        return ResultConflict(
            id=row["id"], batch_id=row["batch_id"], result_ids=json.loads(row["result_ids_json"]),
            statuses=payload.get("statuses", {}), status=row["status"], decision=payload.get("decision"),
            rationale=payload.get("rationale"), confirmed_by=payload.get("confirmed_by"),
        )
