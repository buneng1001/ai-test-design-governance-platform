from fastapi.testclient import TestClient

from test_requirement_review_api import setup_version


def _confirmed_analysis(client: TestClient, select_all: bool = False) -> tuple[int, dict]:
    project_id, version_id = setup_version(client)
    created = client.post(
        f"/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review"
    )
    assert created.status_code == 201
    analysis = created.json()
    selected_ids = [item["requirement_id"] for item in analysis["requirements"]] if select_all else [analysis["requirements"][0]["requirement_id"]]
    assert client.patch(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/selection",
        json={"selected_requirement_ids": selected_ids},
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
    assert {item["source_type"] for item in suggestions} >= {"analysis_inference", "awaiting_confirmation"}

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
    assert candidate["candidate_id"] in confirmed.json()["selected_requirement_ids"]
    promoted = next(item for item in confirmed.json()["atomic_requirements"] if item["candidate_id"] == candidate["candidate_id"])
    assert promoted["stable_requirement_id"] == candidate["stable_requirement_id"]


def test_pending_suggestion_blocks_only_its_related_requirement_in_workflow(client: TestClient) -> None:
    project_id, analysis = _confirmed_analysis(client)
    generated = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/suggestions/generate"
    )
    assert generated.status_code == 200

    workflow = client.get(f"/api/projects/{project_id}/workflow")
    assert workflow.status_code == 200
    suggestions_tab = next(item for item in workflow.json()["tabs"] if item["id"] == "suggestions")
    assert suggestions_tab["status"] == "needs_attention"
    assert "待处置" in suggestions_tab["blocked_reason"]
    assert suggestions_tab["blocked_requirement_ids"] == analysis["selected_requirement_ids"]
    review_tab = next(item for item in workflow.json()["tabs"] if item["id"] == "review")
    assert review_tab["status"] == "current"


def test_pending_suggestion_excludes_only_affected_requirement_from_test_design(client: TestClient) -> None:
    project_id, analysis = _confirmed_analysis(client, select_all=True)
    assert len(analysis["selected_requirement_ids"]) >= 2
    suggestions = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/suggestions/generate"
    ).json()["suggestions"]
    blocked_requirement_id = analysis["selected_requirement_ids"][0]
    for suggestion in suggestions:
        if suggestion["related_requirement_ids"] == [blocked_requirement_id]:
            continue
        assert client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/suggestions/{suggestion['suggestion_id']}",
            json={"disposition": "rejected"},
        ).status_code == 200

    design = client.post(
        f"/api/projects/{project_id}/requirement-versions/{analysis['requirement_version_id']}/test-designs",
        json={},
    )

    assert design.status_code == 201
    assert design.json()["scope_items"]
    assert all(blocked_requirement_id not in item["requirement_ids"] for item in design.json()["scope_items"])
