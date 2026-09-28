from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.ai_run_control_repository import (
    AIRunControlRepository, BatchAlreadyClaimedError, ConcurrentRunResumeError, InputFingerprintMismatchError,
)
from app.project_repository import ProjectRepository


def repository(tmp_path: Path) -> AIRunControlRepository:
    database_path = tmp_path / "run-control.sqlite3"
    ProjectRepository(database_path).migrate()
    return AIRunControlRepository(database_path)


def test_creates_run_before_any_batch_and_persists_validated_checkpoints(tmp_path: Path) -> None:
    controls = repository(tmp_path)

    run = controls.create(project_id=1, workflow="requirement_analysis", payload={"version": 1}, batch_total=2)
    assert run.status == "running"
    assert run.next_batch == 1

    controls.record_validated_batch(run.id, 1, {"items": ["first"]}, ai_run_id=10)
    saved = controls.get(run.id)
    assert saved is not None
    assert saved.completed_count == 1
    assert saved.next_batch == 2
    assert controls.batch_results(run.id) == [{"batch_number": 1, "output": {"items": ["first"]}, "ai_run_id": 10}]


def test_stop_prevents_new_batches_and_resume_is_idempotent(tmp_path: Path) -> None:
    controls = repository(tmp_path)
    run = controls.create(project_id=1, workflow="case_generation", payload={"version": 1}, batch_total=2)
    controls.record_validated_batch(run.id, 1, {"items": ["first"]}, ai_run_id=10)
    stopped = controls.request_stop(run.id)
    assert stopped.status == "stopped"
    assert controls.claim_resume(run.id, run.input_fingerprint).next_batch == 2
    controls.record_validated_batch(run.id, 2, {"items": ["second"]}, ai_run_id=11)
    controls.complete(run.id)
    assert controls.claim_resume(run.id, run.input_fingerprint).status == "completed"
    assert len(controls.batch_results(run.id)) == 2


def test_resume_rejects_changed_input_and_concurrent_claim(tmp_path: Path) -> None:
    controls = repository(tmp_path)
    run = controls.create(project_id=1, workflow="requirement_analysis", payload={"version": 1}, batch_total=2)
    controls.request_stop(run.id)

    with pytest.raises(InputFingerprintMismatchError):
        controls.claim_resume(run.id, "v1:changed")
    controls.claim_resume(run.id, run.input_fingerprint)
    with pytest.raises(ConcurrentRunResumeError):
        controls.claim_resume(run.id, run.input_fingerprint)


def test_final_asset_is_stored_once_and_completed_run_is_reusable(tmp_path: Path) -> None:
    controls = repository(tmp_path)
    run = controls.create(project_id=1, workflow="case_generation", payload={"design": 1}, batch_total=1)

    controls.record_final_asset(run.id, "case_generation", 41)
    controls.record_final_asset(run.id, "case_generation", 42)
    controls.complete(run.id)

    restored = controls.claim_resume(run.id, run.input_fingerprint)
    assert restored.status == "completed"
    assert restored.final_asset_id == 41


def test_checkpoint_payload_keeps_model_output_and_source_references(tmp_path: Path) -> None:
    controls = repository(tmp_path)
    run = controls.create(project_id=1, workflow="requirement_analysis", payload={"version": 1}, batch_total=1)

    controls.record_validated_batch(
        run.id, 1, {"model_output": {"items": ["first"]}, "source_reference_ids": ["source-1"]}, ai_run_id=10,
    )

    assert controls.batch_results(run.id)[0]["output"] == {
        "model_output": {"items": ["first"]}, "source_reference_ids": ["source-1"],
    }


def test_only_one_worker_can_claim_a_batch_and_restart_releases_an_abandoned_claim(tmp_path: Path) -> None:
    controls = repository(tmp_path)
    run = controls.create(project_id=1, workflow="case_generation", payload={"version": 1}, batch_total=2)

    first = controls.claim_next_batch(run.id)
    assert first.batch_number == 1
    with pytest.raises(BatchAlreadyClaimedError):
        controls.claim_next_batch(run.id)

    restarted = AIRunControlRepository(controls.database_path)
    restarted.recover_after_restart()
    resumed = restarted.claim_next_batch(run.id)
    assert resumed.batch_number == 1
    restarted.record_validated_batch(run.id, resumed.batch_number, {"items": ["first"]}, 10, resumed.lease_id)
    assert restarted.claim_next_batch(run.id).batch_number == 2


def test_concurrent_workers_can_claim_the_same_batch_only_once(tmp_path: Path) -> None:
    controls = repository(tmp_path)
    run = controls.create(project_id=1, workflow="requirement_analysis", payload={"version": 1}, batch_total=1)

    def claim() -> str:
        try:
            return controls.claim_next_batch(run.id).lease_id
        except BatchAlreadyClaimedError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: claim(), range(2)))

    assert outcomes.count("blocked") == 1
    assert len([outcome for outcome in outcomes if outcome != "blocked"]) == 1
