import base64

from fastapi.testclient import TestClient


def create_project(client: TestClient) -> int:
    response = client.post(
        "/api/projects",
        json={"name": "AI 运行审计项目", "test_object": "虚构智能采集设备", "software_version": "v1.0.0", "description": "Mock 验证"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_asset(client: TestClient, project_id: int, **overrides: object) -> int:
    payload = {
        "name": "synthetic-v1.md",
        "asset_type": "requirement_material",
        "provenance_kind": "original_synthetic",
        "source": "测试工程师从零创作",
        "usage_permission": "project_owned",
        "model_permission": "allowed",
        "requirement_version": "V1",
        "purpose": "AI 输入验证",
        "content_base64": base64.b64encode(b"synthetic requirement").decode(),
        "change_reason": "首次登记",
    }
    payload.update(overrides)
    response = client.post(f"/api/projects/{project_id}/assets", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def run_input(asset_id: int, **overrides: object) -> dict:
    payload = {
        "task_type": "requirement_review",
        "prompt_version": "requirement-review.v1",
        "input_asset_ids": [asset_id],
        "scenario": "normal",
        "max_retries": 2,
    }
    payload.update(overrides)
    return payload


def test_mock_run_is_deterministic_auditable_and_disposition_is_append_only(client: TestClient) -> None:
    project_id = create_project(client)
    asset_id = create_asset(client, project_id)

    first = client.post(f"/api/projects/{project_id}/ai-runs", json=run_input(asset_id)).json()
    second = client.post(f"/api/projects/{project_id}/ai-runs", json=run_input(asset_id)).json()

    assert first["status"] == "succeeded"
    assert first["validation_status"] == "passed"
    assert first["is_mock"] is True
    assert first["input_asset_versions"] == [{"asset_id": asset_id, "revision": 1}]
    assert first["output"] == second["output"]
    assert first["attempts"][0]["status"] == "succeeded"
    disposition = client.post(
        f"/api/projects/{project_id}/ai-runs/{first['id']}/dispositions",
        json={"decision": "accepted", "reason": "人工确认来源和结构"},
    )
    assert disposition.status_code == 200
    assert disposition.json()["disposition"]["decision"] == "accepted"
    client.post(
        f"/api/projects/{project_id}/ai-runs/{first['id']}/dispositions",
        json={"decision": "modified", "reason": "补充人工边界说明"},
    )
    assert len(client.get(f"/api/projects/{project_id}/ai-runs/{first['id']}").json()["dispositions"]) == 2
    assert client.get(f"/api/projects/{project_id}/ai-runs/{first['id']}").json()["output"] == first["output"]
    assert len(client.get(f"/api/projects/{project_id}/ai-runs").json()) == 2


def test_empty_and_schema_invalid_outputs_are_audited_without_assets(client: TestClient) -> None:
    project_id = create_project(client)
    asset_id = create_asset(client, project_id)

    empty = client.post(
        f"/api/projects/{project_id}/ai-runs", json=run_input(asset_id, scenario="empty")
    ).json()
    invalid = client.post(
        f"/api/projects/{project_id}/ai-runs", json=run_input(asset_id, scenario="invalid_schema")
    ).json()
    missing_source = client.post(
        f"/api/projects/{project_id}/ai-runs", json=run_input(asset_id, scenario="missing_source")
    ).json()

    assert empty["status"] == "succeeded"
    assert empty["output"]["items"] == []
    assert invalid["status"] == "validation_failed"
    assert invalid["validation_status"] == "failed"
    assert invalid["output"] is None
    assert missing_source["status"] == "validation_failed"
    assert missing_source["attempts"][0]["error_code"] == "schema_invalid"


def test_retryable_errors_are_bounded_and_non_retryable_errors_stop_immediately(client: TestClient) -> None:
    project_id = create_project(client)
    asset_id = create_asset(client, project_id)

    timeout = client.post(
        f"/api/projects/{project_id}/ai-runs", json=run_input(asset_id, scenario="timeout", max_retries=2)
    ).json()
    auth = client.post(
        f"/api/projects/{project_id}/ai-runs", json=run_input(asset_id, scenario="authentication_error")
    ).json()

    assert timeout["status"] == "failed"
    assert [attempt["attempt"] for attempt in timeout["attempts"]] == [1, 2, 3]
    assert auth["status"] == "failed"
    assert len(auth["attempts"]) == 1
    assert auth["attempts"][0]["retryable"] is False


def test_unconfigured_real_provider_is_distinguished_from_mock(client: TestClient) -> None:
    project_id = create_project(client)
    asset_id = create_asset(client, project_id)

    response = client.post(
        f"/api/projects/{project_id}/ai-runs",
        json=run_input(asset_id, model_parameters={"provider": "external-provider"}),
    )

    assert response.status_code == 201
    assert response.json()["is_mock"] is False
    assert response.json()["attempts"][0]["error_code"] == "provider_unavailable"


def test_model_context_rejects_truth_unknown_and_missing_assets(client: TestClient) -> None:
    project_id = create_project(client)
    truth_id = create_asset(
        client,
        project_id,
        name="truth.json",
        asset_type="evaluation_truth",
        purpose="隔离的评估真值",
    )
    unknown_id = create_asset(client, project_id, source="", usage_permission="unknown", model_permission="unknown")

    truth_response = client.post(
        f"/api/projects/{project_id}/ai-runs", json=run_input(truth_id)
    )
    unknown_response = client.post(
        f"/api/projects/{project_id}/ai-runs", json=run_input(unknown_id)
    )
    missing_response = client.post(
        f"/api/projects/{project_id}/ai-runs", json=run_input(999)
    )

    assert truth_response.status_code == 422
    assert unknown_response.status_code == 422
    assert missing_response.status_code == 404


def test_audit_export_contains_no_credentials_and_existing_assets_remain_available(client: TestClient) -> None:
    project_id = create_project(client)
    asset_id = create_asset(client, project_id)
    client.post(
        f"/api/projects/{project_id}/ai-runs",
        json=run_input(asset_id, model_parameters={"provider": "mock", "model": "secret-model"}),
    )

    exported = client.get(f"/api/projects/{project_id}/ai-runs/audit-export")

    assert exported.status_code == 200
    assert exported.json()["contract_version"] == "ai-audit.v1"
    assert "api_key" not in exported.text
    assert "authorization" not in exported.text.lower()
    assert client.get(f"/api/projects/{project_id}/model-context-assets").status_code == 200
