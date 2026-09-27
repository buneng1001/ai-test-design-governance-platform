from fastapi.testclient import TestClient

from test_requirement_review_api import setup_version


def _confirmed_analysis(client: TestClient) -> tuple[int, dict]:
    project_id, version_id = setup_version(client)
    created = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review"
    )
    assert created.status_code == 201
    analysis = created.json()
    selected_id = analysis["requirements"][0]["requirement_id"]
    assert client.patch(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/selection",
        json={"selected_requirement_ids": [selected_id]},
    ).status_code == 200
    for finding in analysis["findings"]:
        assert client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/findings/{finding['finding_id']}",
            json={"status": "resolved"},
        ).status_code == 200
    confirmed = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    assert confirmed.status_code == 200
    return project_id, confirmed.json()


def test_suggestions_only_use_confirmed_selected_requirements_and_keep_traceability(client: TestClient) -> None:
    project_id, analysis = _confirmed_analysis(client)

    generated = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/suggestions/generate"
    )

    assert generated.status_code == 200
    suggestions = generated.json()["suggestions"]
    assert {item["direction"] for item in suggestions} == {"normal", "exception", "boundary", "risk"}
    assert all(item["related_requirement_ids"] == analysis["selected_requirement_ids"] for item in suggestions)
    assert all(item["source_references"] and item["impact_scope"] for item in suggestions)
    assert {item["source_type"] for item in suggestions} >= {"material_explicit", "analysis_inference"}

    reloaded = client.get(f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}")
    assert reloaded.status_code == 200
    assert reloaded.json()["suggestions"] == suggestions


def test_four_dispositions_persist_and_accepted_requirement_fact_requires_reconfirmation(client: TestClient) -> None:
    project_id, analysis = _confirmed_analysis(client)
    suggestions = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/suggestions/generate"
    ).json()["suggestions"]
    dispositions = ["accepted", "rejected", "modified", "awaiting_external_confirmation"]

    for suggestion, disposition in zip(suggestions, dispositions, strict=True):
        body = {"disposition": disposition}
        if disposition == "modified":
            body["statement"] = "修改后的补充建议"
        updated = client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/suggestions/{suggestion['suggestion_id']}",
            json=body,
        )
        assert updated.status_code == 200

    reloaded = client.get(f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}").json()
    assert {item["disposition"] for item in reloaded["suggestions"]} == set(dispositions)
    candidates = reloaded["supplemental_requirement_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["decision"] == "pending_confirmation"
    assert candidates[0]["stable_requirement_id"] is None

    confirmed = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/supplemental-requirements/confirm",
        json={"candidate_ids": [candidates[0]["candidate_id"]], "confirmer_name": "测试工程师"},
    )
    assert confirmed.status_code == 200
    candidate = confirmed.json()["supplemental_requirement_candidates"][0]
    assert candidate["decision"] == "confirmed"
    assert candidate["stable_requirement_id"]


def test_pending_suggestion_blocks_only_its_related_requirement_in_workflow(client: TestClient) -> None:
    project_id, analysis = _confirmed_analysis(client)
    generated = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/suggestions/generate"
    )
    assert generated.status_code == 200

    workflow = client.get(f"/api/projects/{project_id}/workflow")
    assert workflow.status_code == 200
    suggestions_tab = next(item for item in workflow.json()["tabs"] if item["id"] == "suggestions")
    assert suggestions_tab["status"] == "current"
    assert "待处置" in suggestions_tab["blocked_reason"]
