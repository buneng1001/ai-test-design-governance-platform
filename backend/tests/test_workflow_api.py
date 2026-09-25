import base64

from fastapi.testclient import TestClient
from test_case_generation_api import _setup as setup_case_generation


def _project(client: TestClient) -> int:
    response = client.post("/api/projects", json={
        "name": "五页签测试设计项目", "test_object": "虚构智能采集设备", "software_version": "v1.0.0",
        "description": "验证主流程恢复。", "settings": {"requirement_language": "zh-CN"},
    })
    assert response.status_code == 201
    return response.json()["id"]


def _publish_version(client: TestClient, project_id: int, name: str) -> int:
    content = base64.b64encode(f"# {name}\\n\\n设备必须保存采集状态。".encode()).decode()
    asset = client.post(f"/api/projects/{project_id}/assets", json={
        "name": f"{name}.md", "asset_type": "requirement_material", "provenance_kind": "original_synthetic",
        "source": "测试工程师从零创作", "usage_permission": "project_owned", "model_permission": "allowed",
        "requirement_version": name, "purpose": "主流程测试", "content_base64": content, "change_reason": "首次登记",
    }).json()
    package = client.post(f"/api/projects/{project_id}/requirement-packages", json={"name": name, "files": [{
        "asset_id": asset["id"], "filename": asset["name"], "media_type": "text/markdown", "content_base64": content,
    }]}).json()
    response = client.post(f"/api/projects/{project_id}/requirement-packages/{package['id']}/publish")
    assert response.status_code == 201
    return response.json()["id"]


def _confirm_preview(client: TestClient, project_id: int, version_id: int) -> None:
    analysis = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review", json={"mode": "mock"},
    ).json()
    for item in analysis["atomic_requirements"]:
        client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/atomic-requirements/{item['candidate_id']}",
            json={"decision": "accepted"},
        )
    for item in analysis["findings"]:
        client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/findings/{item['finding_id']}",
            json={"status": "resolved"},
        )
    response = client.post(f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/confirm", json={
        "confirmer_name": "测试工程师",
    })
    assert response.status_code == 200


def test_workflow_view_unlocks_tabs_and_recovers_from_persisted_assets(client: TestClient) -> None:
    project_id = _project(client)

    initial = client.get(f"/api/projects/{project_id}/workflow").json()
    assert initial["current_step"] == "upload"
    assert initial["tabs"][1]["status"] == "locked"

    version_id = _publish_version(client, project_id, "V1")
    preview = client.get(f"/api/projects/{project_id}/workflow").json()
    assert preview["current_step"] == "preview"
    assert preview["asset_ids"]["requirement_version_id"] == version_id

    _confirm_preview(client, project_id, version_id)
    suggestions = client.get(f"/api/projects/{project_id}/workflow").json()
    assert suggestions["current_step"] == "suggestions"
    assert suggestions["tabs"][2]["status"] == "current"
    assert suggestions["asset_ids"]["requirement_analysis_id"]

    design = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/test-designs", json={}
    ).json()
    draft_workflow = client.get(f"/api/projects/{project_id}/workflow").json()
    assert draft_workflow["current_step"] == "suggestions"
    assert [item["status"] for item in draft_workflow["tabs"]].count("current") == 1
    client.post(f"/api/projects/{project_id}/test-designs/{design['id']}/confirm", json={
        "confirmer_name": "测试工程师",
    })
    restored = client.get(f"/api/projects/{project_id}/workflow").json()
    assert restored["current_step"] == "suggestions"
    assert restored["asset_ids"]["test_design_id"] == design["id"]
    assert restored["tabs"][4]["status"] == "locked"


def test_new_requirement_version_marks_old_downstream_draft_for_reconfirmation(client: TestClient) -> None:
    project_id = _project(client)
    version_id = _publish_version(client, project_id, "V1")
    _confirm_preview(client, project_id, version_id)
    draft = client.post(f"/api/projects/{project_id}/requirement-versions/{version_id}/test-designs", json={}).json()

    _publish_version(client, project_id, "V2")
    workflow = client.get(f"/api/projects/{project_id}/workflow").json()

    assert workflow["tabs"][2]["status"] == "needs_reconfirmation"
    assert workflow["invalidated_draft_ids"] == [draft["id"]]
    assert "需要重新确认" in workflow["tabs"][2]["blocked_reason"]
    confirmation = client.post(f"/api/projects/{project_id}/test-designs/{draft['id']}/confirm", json={
        "confirmer_name": "测试工程师",
    })
    assert confirmation.status_code == 409
    assert "需求版本已更新" in confirmation.json()["detail"]


def test_old_confirmed_design_cannot_generate_cases_after_new_requirement_version(client: TestClient) -> None:
    project_id = _project(client)
    version_id = _publish_version(client, project_id, "V1")
    _confirm_preview(client, project_id, version_id)
    design = client.post(f"/api/projects/{project_id}/requirement-versions/{version_id}/test-designs", json={}).json()
    assert client.post(f"/api/projects/{project_id}/test-designs/{design['id']}/confirm", json={
        "confirmer_name": "测试工程师",
    }).status_code == 200
    _publish_version(client, project_id, "V2")

    response = client.post(f"/api/projects/{project_id}/test-designs/{design['id']}/case-generations", json={})

    assert response.status_code == 409
    assert "需求版本已更新" in response.json()["detail"]


def test_stale_case_review_cannot_be_confirmed_after_new_requirement_version(client: TestClient) -> None:
    project_id, design_id, mapping_id = setup_case_generation(client)
    generation = client.post(f"/api/projects/{project_id}/test-designs/{design_id}/case-generations", json={
        "template_mapping_id": mapping_id, "variants": ["normal"],
    }).json()
    batch = client.post(f"/api/projects/{project_id}/case-generations/{generation['id']}/reviews", json={}).json()
    for suggestion in batch["suggestions"]:
        assert client.patch(
            f"/api/projects/{project_id}/case-review-batches/{batch['id']}/suggestions/{suggestion['id']}",
            json={"decision": "accepted", "reason": "测试工程师确认建议"},
        ).status_code == 200
    _publish_version(client, project_id, "V2")

    response = client.post(f"/api/projects/{project_id}/case-review-batches/{batch['id']}/confirm", json={
        "confirmer_name": "测试工程师", "inclusion": {batch["suggestions"][0]["candidate_id"]: True},
    })

    assert response.status_code == 409
    assert "需求版本已更新" in response.json()["detail"]
