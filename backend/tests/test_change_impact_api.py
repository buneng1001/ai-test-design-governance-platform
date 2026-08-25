import base64

from test_case_generation_api import _setup


def _publish_v2(client, project_id: int, text: str) -> dict:
    content = base64.b64encode(text.encode()).decode()
    asset = client.post(f"/api/projects/{project_id}/assets", json={
        "name": "v2-requirements.md", "asset_type": "requirement_material",
        "provenance_kind": "original_synthetic", "source": "测试工程师从零创作",
        "usage_permission": "project_owned", "model_permission": "allowed", "requirement_version": "V2",
        "purpose": "需求变更", "content_base64": content, "change_reason": "V2 独立需求资料",
    }).json()
    package = client.post(f"/api/projects/{project_id}/requirement-packages", json={
        "name": "V2 需求资料包", "files": [{
            "asset_id": asset["id"], "filename": "v2-requirements.md", "media_type": "text/markdown",
            "content_base64": content,
        }],
    }).json()
    version = client.post(
        f"/api/projects/{project_id}/requirement-packages/{package['id']}/publish"
    ).json()
    review = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version['id']}/requirement-review"
    ).json()
    for candidate in review["atomic_requirements"]:
        client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{review['id']}"
            f"/atomic-requirements/{candidate['candidate_id']}",
            json={"decision": "accepted"},
        )
    for finding in review["findings"]:
        client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{review['id']}"
            f"/findings/{finding['finding_id']}",
            json={"status": "resolved"},
        )
    confirmed = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{review['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    assert confirmed.status_code == 200, confirmed.text
    return version


def test_v1_v2_impact_requires_confirmation_and_confirms_regression(client) -> None:
    project_id, design_id, mapping_id = _setup(client)
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal"]},
    ).json()
    review_batch = client.post(
        f"/api/projects/{project_id}/case-generations/{generation['id']}/reviews", json={}
    ).json()
    for suggestion in review_batch["suggestions"]:
        client.patch(
            f"/api/projects/{project_id}/case-review-batches/{review_batch['id']}"
            f"/suggestions/{suggestion['id']}",
            json={"decision": "accepted", "reason": "测试工程师确认"},
        )
    confirmed = client.post(
        f"/api/projects/{project_id}/case-review-batches/{review_batch['id']}/confirm",
        json={"confirmer_name": "测试工程师", "inclusion": {
            review_batch["suggestions"][0]["candidate_id"]: True
        }},
    )
    assert confirmed.status_code == 200, confirmed.text
    versions = client.get(f"/api/projects/{project_id}/requirement-versions").json()
    v1 = versions[0]
    v2 = _publish_v2(client, project_id, "设备必须保存更新状态。\n")
    analysis = client.post(
        f"/api/projects/{project_id}/change-impact-analyses",
        json={"base_version_id": v1["id"], "target_version_id": v2["id"]},
    )
    assert analysis.status_code == 201, analysis.text
    payload = analysis.json()
    assert payload["status"] == "pending_change_confirmation"
    assert any(item["base_source_reference"] and item["target_source_reference"] for item in payload["changes"])

    before = client.get(f"/api/projects/{project_id}/case-review-batches/{review_batch['id']}").json()
    assert any(item["participation_status"] == "not_included" for item in before["revisions"])
    confirmed = client.post(
        f"/api/projects/{project_id}/change-impact-analyses/{payload['id']}/confirm",
        json={"confirmer_name": "测试工程师", "decisions": {item["id"]: "confirmed" for item in payload["changes"]}},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    after = client.get(f"/api/projects/{project_id}/case-review-batches/{review_batch['id']}").json()
    assert any(item["participation_status"] == "pending_impact" for item in after["revisions"])

    selection = client.post(
        f"/api/projects/{project_id}/change-impact-analyses/{payload['id']}/regression-selection"
    )
    assert selection.status_code == 201, selection.text
    selection_payload = selection.json()
    assert selection_payload["candidates"]
    final = client.post(
        f"/api/projects/{project_id}/regression-selections/{selection_payload['id']}/confirm",
        json={
            "confirmer_name": "测试工程师",
            "decisions": {item["stable_case_id"]: True for item in selection_payload["candidates"]},
            "reasons": {item["stable_case_id"]: "需求变更后确认回归" for item in selection_payload["candidates"]},
        },
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "confirmed"


def test_change_analysis_rejects_unconfirmed_requirement_versions(client) -> None:
    project_id, _, _ = _setup(client)
    version = client.get(f"/api/projects/{project_id}/requirement-versions").json()[0]
    response = client.post(
        f"/api/projects/{project_id}/change-impact-analyses",
        json={"base_version_id": version["id"], "target_version_id": version["id"]},
    )
    assert response.status_code == 422
