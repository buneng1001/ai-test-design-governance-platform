from pathlib import Path
from threading import Event, Thread

from fastapi.testclient import TestClient

from app.main import create_app
from app.ai_service import ModelResponse
from test_case_generation_api import _setup
from test_requirement_review_api import setup_version


def test_requirement_analysis_start_returns_run_id_before_model_call(client: TestClient) -> None:
    project_id, version_id = setup_version(client)

    started = client.post(f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs", json={"batch_size": 1})

    assert started.status_code == 201, started.text
    assert started.json()["status"] == "running"
    assert client.get(f"/api/projects/{project_id}/ai-runs").json() == []


def test_case_generation_start_returns_run_id_before_model_call(client: TestClient) -> None:
    project_id, design_id, mapping_id = _setup(client)
    existing_run_count = len(client.get(f"/api/projects/{project_id}/ai-runs").json())

    started = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs",
        json={"template_mapping_id": mapping_id, "batch_size": 1},
    )

    assert started.status_code == 201, started.text
    assert started.json()["status"] == "running"
    assert len(client.get(f"/api/projects/{project_id}/ai-runs").json()) == existing_run_count


def test_requirement_analysis_rejects_changed_normalized_input_on_advance(client: TestClient) -> None:
    project_id, version_id = setup_version(client)
    run_id = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs", json={"mode": "mock"},
    ).json()["id"]

    changed = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/advance",
        json={"mode": "template"},
    )

    assert changed.status_code == 409


def test_case_generation_rejects_changed_normalized_input_on_advance(client: TestClient) -> None:
    project_id, design_id, mapping_id = _setup(client)
    run_id = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs",
        json={"template_mapping_id": mapping_id, "mode": "mock"},
    ).json()["id"]

    changed = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/advance",
        json={"template_mapping_id": mapping_id, "mode": "template"},
    )

    assert changed.status_code == 409


def test_requirement_analysis_advances_stops_and_resumes_without_duplicate_asset(client: TestClient) -> None:
    project_id, version_id = setup_version(client)
    started = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs", json={"batch_size": 1},
    ).json()
    run_id = started["id"]

    first = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/advance", json={"batch_size": 1},
    )
    assert first.status_code == 200 and first.json()["completed_count"] == 1
    assert client.post(f"/api/projects/{project_id}/ai-workflow-runs/{run_id}/stop").json()["status"] == "stopped"
    stopped = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/advance", json={"batch_size": 1},
    )
    assert stopped.status_code == 409
    completed = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/resume", json={"batch_size": 1},
    )
    assert completed.status_code == 200 and completed.json()["run_control_id"] == run_id
    repeated = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/advance", json={"batch_size": 1},
    )
    assert repeated.json()["id"] == completed.json()["id"]


def test_case_generation_stops_resumes_and_reuses_completed_asset(client: TestClient) -> None:
    project_id, design_id, mapping_id = _setup(client)
    started = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs",
        json={"template_mapping_id": mapping_id, "batch_size": 1},
    ).json()
    run_id = started["id"]
    assert client.post(f"/api/projects/{project_id}/ai-workflow-runs/{run_id}/stop").json()["status"] == "stopped"
    blocked = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/advance",
        json={"template_mapping_id": mapping_id, "batch_size": 1},
    )
    assert blocked.status_code == 409
    completed = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/resume",
        json={"template_mapping_id": mapping_id, "batch_size": 1},
    )
    while "run_control_id" not in completed.json():
        completed = client.post(
            f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/advance",
            json={"template_mapping_id": mapping_id, "batch_size": 1},
        )
    assert completed.status_code == 200 and completed.json()["run_control_id"] == run_id
    repeated = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/advance",
        json={"template_mapping_id": mapping_id, "batch_size": 1},
    )
    assert repeated.json()["id"] == completed.json()["id"]


def test_requirement_analysis_resumes_from_checkpoint_after_application_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "restart-requirement.sqlite3"
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local")) as first:
        project_id, version_id = setup_version(first)
        run_id = first.post(
            f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs", json={"batch_size": 1},
        ).json()["id"]
        assert first.post(
            f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/advance", json={"batch_size": 1},
        ).status_code == 200
        first.post(f"/api/projects/{project_id}/ai-workflow-runs/{run_id}/stop")
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local")) as restarted:
        completed = restarted.post(
            f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/resume", json={"batch_size": 1},
        )

    assert completed.status_code == 200
    assert completed.json()["run_control_id"] == run_id


def test_case_generation_resumes_from_checkpoint_after_application_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "restart-case.sqlite3"
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local")) as first:
        project_id, design_id, mapping_id = _setup(first)
        run_id = first.post(
            f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs",
            json={"template_mapping_id": mapping_id, "batch_size": 1},
        ).json()["id"]
        assert first.post(f"/api/projects/{project_id}/ai-workflow-runs/{run_id}/stop").status_code == 200
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local")) as restarted:
        result = restarted.post(
            f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/resume",
            json={"template_mapping_id": mapping_id, "batch_size": 1},
        )
        while result.status_code == 200 and "run_control_id" not in result.json():
            result = restarted.post(
                f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/advance",
                json={"template_mapping_id": mapping_id, "batch_size": 1},
            )

    assert result.status_code == 200
    assert result.json()["run_control_id"] == run_id


class BlockingRetryService:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.calls = 0

    def complete(self, _request: object) -> ModelResponse:
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=5)
        return ModelResponse(error_code="timeout", retryable=True)


class BlockingSuccessService(BlockingRetryService):
    def complete(self, request: object) -> ModelResponse:
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=5)
        from app.ai_service import MockModelService
        return MockModelService().complete(request)  # type: ignore[arg-type]


def test_stop_during_retryable_requirement_call_prevents_second_model_call(tmp_path: Path) -> None:
    database_path = tmp_path / "blocking-stop.sqlite3"
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local")) as setup_client:
        project_id, version_id = setup_version(setup_client)
        run_id = setup_client.post(
            f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs", json={"batch_size": 1},
        ).json()["id"]
    service = BlockingRetryService()
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local", model_service=service)) as client:
        result: dict[str, object] = {}
        worker = Thread(target=lambda: result.setdefault("response", client.post(
            f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/advance", json={"batch_size": 1},
        )))
        worker.start()
        assert service.started.wait(timeout=2)
        assert client.post(f"/api/projects/{project_id}/ai-workflow-runs/{run_id}/stop").status_code == 200
        service.release.set()
        worker.join(timeout=3)

    assert service.calls == 1
    assert result["response"].status_code == 409


def test_stop_during_retryable_case_call_prevents_second_model_call(tmp_path: Path) -> None:
    database_path = tmp_path / "blocking-case-stop.sqlite3"
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local")) as setup_client:
        project_id, design_id, mapping_id = _setup(setup_client)
        run_id = setup_client.post(
            f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs",
            json={"template_mapping_id": mapping_id, "batch_size": 1},
        ).json()["id"]
    service = BlockingRetryService()
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local", model_service=service)) as client:
        result: dict[str, object] = {}
        worker = Thread(target=lambda: result.setdefault("response", client.post(
            f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/advance",
            json={"template_mapping_id": mapping_id, "batch_size": 1},
        )))
        worker.start()
        assert service.started.wait(timeout=2)
        assert client.post(f"/api/projects/{project_id}/ai-workflow-runs/{run_id}/stop").status_code == 200
        service.release.set()
        worker.join(timeout=3)

    assert service.calls == 1
    assert result["response"].status_code == 409


def test_concurrent_requirement_advances_invoke_the_model_once(tmp_path: Path) -> None:
    database_path = tmp_path / "concurrent-advance.sqlite3"
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local")) as setup_client:
        project_id, version_id = setup_version(setup_client)
        run_id = setup_client.post(
            f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs", json={"batch_size": 1},
        ).json()["id"]
    service = BlockingSuccessService()
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local", model_service=service)) as client:
        first: dict[str, object] = {}
        worker = Thread(target=lambda: first.setdefault("response", client.post(
            f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/advance", json={"batch_size": 1},
        )))
        worker.start()
        assert service.started.wait(timeout=2)
        competing = client.post(
            f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review-runs/{run_id}/advance", json={"batch_size": 1},
        )
        service.release.set()
        worker.join(timeout=3)

    assert competing.status_code == 409
    assert service.calls == 1
    assert first["response"].status_code == 200


def test_concurrent_case_advances_invoke_the_model_once(tmp_path: Path) -> None:
    database_path = tmp_path / "concurrent-case-advance.sqlite3"
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local")) as setup_client:
        project_id, design_id, mapping_id = _setup(setup_client)
        run_id = setup_client.post(
            f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs",
            json={"template_mapping_id": mapping_id, "batch_size": 1},
        ).json()["id"]
    service = BlockingSuccessService()
    with TestClient(create_app(database_path, local_credentials_path=tmp_path / ".env.local", model_service=service)) as client:
        first: dict[str, object] = {}
        worker = Thread(target=lambda: first.setdefault("response", client.post(
            f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/advance",
            json={"template_mapping_id": mapping_id, "batch_size": 1},
        )))
        worker.start()
        assert service.started.wait(timeout=2)
        competing = client.post(
            f"/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/advance",
            json={"template_mapping_id": mapping_id, "batch_size": 1},
        )
        service.release.set()
        worker.join(timeout=3)

    assert competing.status_code == 409
    assert service.calls == 1
    assert first["response"].status_code == 200
