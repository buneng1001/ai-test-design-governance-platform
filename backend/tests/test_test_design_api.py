import base64

from fastapi.testclient import TestClient


def _setup_confirmed_version(client: TestClient) -> tuple[int, int]:
    content = base64.b64encode("# Rules\n\n设备必须保存状态。\n".encode()).decode()
    project = client.post(
        "/api/projects",
        json={
            "name": "测试设计项目",
            "test_object": "虚构智能采集设备",
            "software_version": "v1.0.0",
            "description": "维度、风险和自动化设计",
            "settings": {"requirement_language": "zh-CN"},
        },
    ).json()
    asset = client.post(
        f"/api/projects/{project['id']}/assets",
        json={
            "name": "requirements.md",
            "asset_type": "requirement_material",
            "provenance_kind": "original_synthetic",
            "source": "测试工程师从零创作",
            "usage_permission": "project_owned",
            "model_permission": "allowed",
            "requirement_version": "V1",
            "purpose": "需求评审",
            "content_base64": content,
            "change_reason": "首次登记",
        },
    ).json()
    package = client.post(
        f"/api/projects/{project['id']}/requirement-packages",
        json={
            "name": "V1 需求资料包",
            "files": [{
                "asset_id": asset["id"],
                "filename": "requirements.md",
                "media_type": "text/markdown",
                "content_base64": content,
            }],
        },
    ).json()
    version = client.post(
        f"/api/projects/{project['id']}/requirement-packages/{package['id']}/publish"
    ).json()
    analysis = client.post(
        f"/api/projects/{project['id']}/requirement-versions/{version['id']}/requirement-review"
    ).json()
    for candidate in analysis["atomic_requirements"]:
        client.patch(
            f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}"
            f"/atomic-requirements/{candidate['candidate_id']}",
            json={"decision": "accepted"},
        )
    for finding in analysis["findings"]:
        client.patch(
            f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}"
            f"/findings/{finding['finding_id']}",
            json={"status": "resolved"},
        )
    client.post(
        f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    return project["id"], version["id"]


def test_design_scope_risk_automation_and_confirmation(client: TestClient) -> None:
    project_id, version_id = _setup_confirmed_version(client)
    created = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/test-designs",
        json={},
    )
    assert created.status_code == 201
    design = created.json()
    assert design["status"] == "draft"
    assert design["ai_run_id"]
    assert design["scope_items"][0]["requirement_ids"]
    assert design["risks"][0]["factors"][0]["source_references"]

    dimension = client.post(
        f"/api/projects/{project_id}/test-designs/{design['id']}/dimensions",
        json={"name": "稳定性", "sort_order": 5},
    )
    assert dimension.status_code == 200
    history = client.get(f"/api/projects/{project_id}/test-designs/{design['id']}/history")
    assert history.status_code == 200
    assert history.json()[-1]["event_type"] == "dimension_added"

    scope = design["scope_items"][0]
    factor = {
        "key": "business_impact",
        "name": "业务影响",
        "score": 5,
        "weight": 2,
        "suggested_score": 3,
        "suggestion_reason": "需求影响设备状态保存",
        "source_references": design["risks"][0]["factors"][0]["source_references"],
    }
    risk = client.patch(
        f"/api/projects/{project_id}/test-designs/{design['id']}/risks/{scope['id']}",
        json={"factors": [factor], "adjustment_reason": "业务关键路径，人工上调"},
    )
    assert risk.status_code == 200
    updated_risk = next(item for item in risk.json()["risks"] if item["scope_item_id"] == scope["id"])
    assert updated_risk["final_score"] == 100
    automation = client.patch(
        f"/api/projects/{project_id}/test-designs/{design['id']}/automation/{scope['id']}",
        json={
            "factors": {
                "regression_value": 5,
                "determinism": 5,
                "environment_control": 4,
                "saving_benefit": 5,
                "maintenance_cost": 1,
                "manual_observation": 1,
            },
            "decision": "priority_automation",
            "decision_reason": "回归频繁且判定确定",
        },
    )
    assert automation.status_code == 200
    confirmed = client.post(
        f"/api/projects/{project_id}/test-designs/{design['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    immutable = client.post(
        f"/api/projects/{project_id}/test-designs/{design['id']}/dimensions",
        json={"name": "安全"},
    )
    assert immutable.status_code == 409


def test_dimension_used_by_scope_cannot_be_deleted(client: TestClient) -> None:
    project_id, version_id = _setup_confirmed_version(client)
    design = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/test-designs",
        json={},
    ).json()
    result = client.delete(
        f"/api/projects/{project_id}/test-designs/{design['id']}/dimensions/"
        f"{design['scope_items'][0]['primary_dimension_id']}"
    )
    assert result.status_code == 409
