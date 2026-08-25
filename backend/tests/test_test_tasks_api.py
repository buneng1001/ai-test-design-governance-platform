import json

from test_case_generation_api import _setup


def _confirmed_batch(client) -> tuple[int, dict]:
    project_id, design_id, mapping_id = _setup(client)
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal"]},
    ).json()
    batch = client.post(
        f"/api/projects/{project_id}/case-generations/{generation['id']}/reviews", json={}
    ).json()
    for suggestion in batch["suggestions"]:
        client.patch(
            f"/api/projects/{project_id}/case-review-batches/{batch['id']}/suggestions/{suggestion['id']}",
            json={"decision": "accepted", "reason": "测试工程师完成 AI 建议处置"},
        )
    confirmed = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/confirm",
        json={
            "confirmer_name": "测试工程师",
            "inclusion": {batch["suggestions"][0]["candidate_id"]: True},
        },
    )
    assert confirmed.status_code == 200
    return project_id, confirmed.json()


def test_task_publication_requires_confirmation_and_exports_one_contract(client) -> None:
    project_id, batch = _confirmed_batch(client)
    case_id = batch["revisions"][-1]["stable_case_id"]
    task_url = f"/api/projects/{project_id}/case-review-batches/{batch['id']}/test-tasks"
    published = client.post(
        task_url,
        json={
            "confirmer_name": "测试工程师",
            "execution_target": "test_execution_diagnostics",
            "stable_case_ids": [case_id],
            "target_extension": {"profile": "offline-demo"},
        },
    )
    assert published.status_code == 201
    task = published.json()
    assert task["contract_version"] == "test-task.v1"
    assert task["execution_scope"] == "selected"
    assert task["cases"][0]["stable_case_id"] == case_id
    assert "target_extension" not in task

    json_file = client.get(f"/api/projects/{project_id}/test-tasks/{task['task_id']}/download")
    yaml_file = client.get(
        f"/api/projects/{project_id}/test-tasks/{task['task_id']}/download?format=yaml"
    )
    assert json.loads(json_file.text)["task_id"] == task["task_id"]
    assert "contract_version: test-task.v1" in yaml_file.text


def test_task_gate_target_extension_and_adapter_round_trip(client) -> None:
    project_id, batch = _confirmed_batch(client)
    case_id = batch["revisions"][-1]["stable_case_id"]
    task_url = f"/api/projects/{project_id}/case-review-batches/{batch['id']}/test-tasks"
    invalid_extension = client.post(
        task_url,
        json={
            "confirmer_name": "测试工程师",
            "execution_target": "manual",
            "stable_case_ids": [case_id],
            "target_extension": {"profile": "not-allowed"},
        },
    )
    assert invalid_extension.status_code == 422

    task = client.post(
        task_url,
        json={
            "confirmer_name": "测试工程师",
            "execution_target": "test_execution_diagnostics",
            "stable_case_ids": [case_id],
        },
    ).json()
    target = client.post(
        "/api/test-task-adapters/test-execution-diagnostics",
        json={"task": task, "target_extension": {"profile": "offline-demo"}},
    )
    assert target.status_code == 200
    target_payload = target.json()
    assert target_payload["task_id"] == task["task_id"]
    assert target_payload["cases"][0]["case_revision_id"] == task["cases"][0]["case_revision_id"]

    feedback = client.post(
        "/api/test-task-adapters/test-execution-diagnostics/results",
        json={
            "task_id": task["task_id"],
            "task_version": task["task_version"],
            "stable_case_id": case_id,
            "case_revision_id": task["cases"][0]["case_revision_id"],
            "verdict": "passed",
            "evidence_references": ["evidence://demo/1"],
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["contract_version"] == "run-result-feedback.v1"
    assert feedback.json()["evidence_references"] == ["evidence://demo/1"]

    incompatible = client.post(
        "/api/test-task-adapters/test-execution-diagnostics",
        json={"task": {**task, "contract_version": "test-task.v0"}},
    )
    assert incompatible.status_code == 422


def test_task_publication_before_case_confirmation_is_rejected(client) -> None:
    project_id, design_id, mapping_id = _setup(client)
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal"]},
    ).json()
    batch = client.post(
        f"/api/projects/{project_id}/case-generations/{generation['id']}/reviews", json={}
    ).json()
    response = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/test-tasks",
        json={
            "confirmer_name": "测试工程师",
            "execution_target": "unspecified",
            "stable_case_ids": ["case-not-confirmed"],
        },
    )
    assert response.status_code == 409
