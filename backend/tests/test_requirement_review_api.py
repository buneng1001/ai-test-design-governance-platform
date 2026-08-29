import base64

from fastapi.testclient import TestClient


def encoded(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def setup_version(client: TestClient) -> tuple[int, int]:
    content = "# Rules\n\n设备必须保存状态。\n".encode()
    project = client.post(
        "/api/projects",
        json={
            "name": "需求评审项目",
            "test_object": "虚构智能采集设备",
            "software_version": "v1.0.0",
            "description": "需求确认闭环",
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
            "content_base64": encoded(content),
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
                "content_base64": encoded(content),
            }],
        },
    ).json()
    version = client.post(
        f"/api/projects/{project['id']}/requirement-packages/{package['id']}/publish"
    ).json()
    return project["id"], version["id"]


def test_requirement_review_requires_human_confirmation_and_keeps_history(client: TestClient) -> None:
    project_id, version_id = setup_version(client)
    response = client.post(f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review")
    assert response.status_code == 201
    analysis = response.json()
    assert analysis["status"] == "draft"
    candidate = analysis["atomic_requirements"][0]
    finding = analysis["findings"][0]
    assert candidate["stable_requirement_id"] is None
    assert candidate["source_reference"]["locator"]

    blocked = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    assert blocked.status_code == 409

    for item in analysis["atomic_requirements"]:
        accepted = client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}"
            f"/atomic-requirements/{item['candidate_id']}",
            json={"statement": item["statement"], "decision": "accepted"},
        )
        assert accepted.status_code == 200
    assert all(
        item["stable_requirement_id"]
        for item in accepted.json()["atomic_requirements"]
    )
    finding_update = client.patch(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/findings/{finding['finding_id']}",
        json={"status": "resolved"},
    )
    assert finding_update.status_code == 200
    confirmed = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    history = client.get(f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/history")
    assert history.status_code == 200
    assert [item["event_type"] for item in history.json()] == [
        "analysis_created",
        "atomic_requirement_updated",
        "atomic_requirement_updated",
        "review_finding_updated",
        "requirement_confirmed",
    ]

    immutable = client.patch(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}"
        f"/atomic-requirements/{candidate['candidate_id']}",
        json={"decision": "rejected"},
    )
    assert immutable.status_code == 409


def test_visual_inference_cannot_be_confirmed_as_fact_without_decision(client: TestClient) -> None:
    project_id, version_id = setup_version(client)
    analysis = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review"
    ).json()
    assert analysis["visual_inferences"] == []
    assert all(item["decision"] != "accepted" for item in analysis["atomic_requirements"])


def test_structured_analysis_contains_semantic_items_and_traceable_sources(client: TestClient) -> None:
    project_id, version_id = setup_version(client)
    response = client.post(f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review")
    assert response.status_code == 201
    analysis = response.json()
    assert analysis["requirements"][0]["module"]
    assert analysis["test_items"][0]["requirement_ids"]
    assert analysis["acceptance_criteria"][0]["source_references"]
    assert analysis["ai_run_id"]


def test_real_analysis_requires_a_session_model_configuration(client: TestClient) -> None:
    project_id, version_id = setup_version(client)
    response = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review",
        json={"mode": "real"},
    )
    assert response.status_code == 422
    assert "未配置真实模型" in response.json()["detail"]


def test_candidate_edit_rejects_unknown_source_reference_and_supports_split(client: TestClient) -> None:
    project_id, version_id = setup_version(client)
    analysis = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review"
    ).json()
    candidate = analysis["atomic_requirements"][0]
    invalid = client.patch(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}"
        f"/atomic-requirements/{candidate['candidate_id']}",
        json={"source_reference": {
            "reference_id": "missing",
            "asset_id": 999,
            "filename": "missing.md",
            "locator": "lines:1-1",
        }},
    )
    assert invalid.status_code == 422
    split = client.patch(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}"
        f"/atomic-requirements/{candidate['candidate_id']}",
        json={"split_into": ["设备必须保存状态。", "设备必须保留状态历史。"]},
    )
    assert split.status_code == 200
    assert len(split.json()["atomic_requirements"]) == len(analysis["atomic_requirements"]) + 2


def test_requirement_table_selection_and_conflict_decision_are_independent_views(client: TestClient) -> None:
    content_a = encoded("SRS: 设备必须保存状态。\n".encode())
    content_b = encoded("Implementation: 设备只保存最近状态。\n".encode())
    project = client.post("/api/projects", json={
        "name": "冲突治理项目", "test_object": "虚构设备", "software_version": "v1",
    }).json()
    assets = []
    for filename, content in (("SRS.md", content_a), ("implementation.md", content_b)):
        assets.append(client.post(f"/api/projects/{project['id']}/assets", json={
            "name": filename, "asset_type": "requirement_material", "provenance_kind": "original_synthetic",
            "source": "测试工程师从零创作", "usage_permission": "project_owned", "model_permission": "allowed",
            "requirement_version": "V1", "purpose": "冲突测试", "content_base64": content,
            "change_reason": "首次登记",
        }).json())
    package = client.post(f"/api/projects/{project['id']}/requirement-packages", json={
        "files": [{"asset_id": asset["id"], "filename": asset["name"], "media_type": "text/markdown",
                   "content_base64": content} for asset, content in zip(assets, (content_a, content_b), strict=True)],
    }).json()
    version = client.post(f"/api/projects/{project['id']}/requirement-packages/{package['id']}/publish").json()
    analysis = client.post(
        f"/api/projects/{project['id']}/requirement-versions/{version['id']}/requirement-review"
    ).json()
    assert analysis["selected_requirement_ids"] == [item["requirement_id"] for item in analysis["requirements"]]
    selected = client.patch(
        f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/selection",
        json={"selected_requirement_ids": [analysis["requirements"][0]["requirement_id"]]},
    )
    assert selected.status_code == 200
    conflicts = client.get(
        f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/conflicts"
    )
    assert conflicts.status_code == 200
    conflict = conflicts.json()[0]
    assert conflict["srs_source"]["filename"] == "SRS.md"
    resolved = client.patch(
        f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/conflicts/{conflict['conflict_id']}",
        json={"decision": "srs_preferred", "confirmer_name": "测试工程师"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["conflicts"][0]["decision"] == "srs_preferred"
