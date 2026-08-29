import base64
import hashlib

from fastapi.testclient import TestClient


def create_project(client: TestClient) -> int:
    response = client.post(
        "/api/projects",
        json={
            "name": "资产护栏测试项目",
            "test_object": "虚构智能采集设备",
            "software_version": "v1.0.0",
            "description": "只验证资产来源记录。",
            "settings": {"requirement_language": "zh-CN"},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def encoded(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def asset_input(**overrides: object) -> dict:
    payload = {
        "name": "synthetic-v1.md",
        "asset_type": "requirement_material",
        "provenance_kind": "original_synthetic",
        "source": "测试工程师从零创作",
        "usage_permission": "project_owned",
        "model_permission": "allowed",
        "requirement_version": "V1",
        "purpose": "需求评审演示",
        "content_base64": encoded("原创合成需求".encode()),
        "change_reason": "首次登记",
    }
    payload.update(overrides)
    return payload


def test_original_synthetic_asset_is_registered_with_deterministic_hash(client: TestClient) -> None:
    project_id = create_project(client)
    response = client.post(f"/api/projects/{project_id}/assets", json=asset_input())

    assert response.status_code == 201
    asset = response.json()
    assert asset["sha256"] == hashlib.sha256("原创合成需求".encode()).hexdigest()
    assert asset["revision"] == 1
    assert asset["boundary"] == "original_synthetic"
    assert asset["can_enter_requirement_package"] is True
    assert asset["can_enter_model_context"] is True
    assert asset["reason"] == "原创合成资产已登记，允许按登记用途使用"


def test_public_asset_and_prohibited_asset_have_explicit_boundaries(client: TestClient) -> None:
    project_id = create_project(client)
    public_response = client.post(
        f"/api/projects/{project_id}/assets",
        json=asset_input(
            name="public-api.md",
            provenance_kind="public_authorized",
            source="https://example.test/public-api",
            usage_permission="public_license",
            model_permission="denied",
            purpose="人工参考",
        ),
    )
    prohibited_response = client.post(
        f"/api/projects/{project_id}/assets",
        json=asset_input(
            name="forbidden.md",
            provenance_kind="prohibited",
            source="禁止使用的材料",
            usage_permission="prohibited",
        ),
    )

    assert public_response.status_code == 201
    assert public_response.json()["boundary"] == "public_authorized"
    assert public_response.json()["can_enter_requirement_package"] is True
    assert public_response.json()["can_enter_model_context"] is False
    assert public_response.json()["reason"] == "公开授权资产可用于登记用途，但未获模型使用权限"
    assert prohibited_response.status_code == 201
    assert prohibited_response.json()["boundary"] == "prohibited"
    assert prohibited_response.json()["can_enter_requirement_package"] is False
    assert prohibited_response.json()["can_enter_model_context"] is False
    assert prohibited_response.json()["reason"] == "资产被明确标记为禁止使用"


def test_unknown_asset_is_recorded_but_blocked_from_downstream_use(client: TestClient) -> None:
    project_id = create_project(client)
    response = client.post(
        f"/api/projects/{project_id}/assets",
        json=asset_input(source="", usage_permission="unknown", model_permission="unknown"),
    )

    assert response.status_code == 201
    asset = response.json()
    assert asset["boundary"] == "unknown"
    assert asset["can_enter_requirement_package"] is False
    assert asset["can_enter_model_context"] is False
    assert asset["reason"] == "缺少来源或明确使用权限，属于来源不明资产"


def test_inconsistent_source_boundary_and_permission_is_blocked(client: TestClient) -> None:
    project_id = create_project(client)
    response = client.post(
        f"/api/projects/{project_id}/assets",
        json=asset_input(provenance_kind="public_authorized", usage_permission="project_owned"),
    )

    assert response.status_code == 201
    assert response.json()["boundary"] == "unknown"
    assert response.json()["can_enter_requirement_package"] is False
    assert response.json()["reason"] == "来源边界与使用权限不一致，属于来源不明资产"


def test_hash_verification_detects_changed_content(client: TestClient) -> None:
    project_id = create_project(client)
    asset = client.post(f"/api/projects/{project_id}/assets", json=asset_input()).json()

    unchanged = client.post(
        f"/api/projects/{project_id}/assets/{asset['id']}/verify",
        json={"content_base64": asset_input()["content_base64"]},
    )
    changed = client.post(
        f"/api/projects/{project_id}/assets/{asset['id']}/verify",
        json={"content_base64": encoded("内容已经变化".encode())},
    )

    assert unchanged.status_code == 200
    assert unchanged.json()["matches"] is True
    assert changed.status_code == 200
    assert changed.json()["matches"] is False
    assert changed.json()["expected_sha256"] == asset["sha256"]
    assert changed.json()["actual_sha256"] == hashlib.sha256("内容已经变化".encode()).hexdigest()


def test_provenance_changes_append_history_and_model_context_uses_latest_revision(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    created = client.post(f"/api/projects/{project_id}/assets", json=asset_input()).json()

    updated_response = client.put(
        f"/api/projects/{project_id}/assets/{created['id']}",
        json=asset_input(
            source="来源待重新确认",
            usage_permission="unknown",
            model_permission="unknown",
            content_base64=encoded("修订后的内容".encode()),
            change_reason="内容与授权范围发生变化",
        ),
    )
    history_response = client.get(f"/api/projects/{project_id}/assets/{created['id']}/history")
    context_response = client.get(f"/api/projects/{project_id}/model-context-assets")

    assert updated_response.status_code == 200
    assert updated_response.json()["revision"] == 2
    assert updated_response.json()["boundary"] == "unknown"
    history = history_response.json()
    assert [item["revision"] for item in history] == [1, 2]
    assert history[0]["sha256"] == created["sha256"]
    assert history[1]["sha256"] != created["sha256"]
    assert context_response.status_code == 200
    assert context_response.json() == []


def test_model_context_filters_assets_without_explicit_permission(client: TestClient) -> None:
    project_id = create_project(client)
    allowed = client.post(f"/api/projects/{project_id}/assets", json=asset_input()).json()
    client.post(
        f"/api/projects/{project_id}/assets",
        json=asset_input(
            name="truth.json",
            asset_type="evaluation_truth",
            model_permission="allowed",
            purpose="AI 效果评价",
        ),
    )
    client.post(
        f"/api/projects/{project_id}/assets",
        json=asset_input(name="unknown.md", source="", usage_permission="unknown"),
    )

    response = client.get(f"/api/projects/{project_id}/model-context-assets")

    assert response.status_code == 200
    assert [asset["id"] for asset in response.json()] == [allowed["id"]]

    truth = client.get(f"/api/projects/{project_id}/assets").json()[1]
    assert truth["can_enter_requirement_package"] is False
    assert truth["can_enter_model_context"] is False
    assert truth["reason"] == "评估真值必须与普通模型上下文隔离"


def test_asset_endpoints_reject_missing_project_and_invalid_content(client: TestClient) -> None:
    missing_project = client.post("/api/projects/999/assets", json=asset_input())
    project_id = create_project(client)
    invalid_content = client.post(
        f"/api/projects/{project_id}/assets",
        json=asset_input(content_base64="not base64!"),
    )

    assert missing_project.status_code == 404
    assert missing_project.json() == {"detail": "测试设计项目不存在"}
    assert invalid_content.status_code == 422
