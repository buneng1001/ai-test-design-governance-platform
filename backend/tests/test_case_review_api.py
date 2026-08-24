from test_case_generation_api import _setup


def _create_generation(client) -> tuple[int, int]:
    project_id, design_id, mapping_id = _setup(client)
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal"]},
    )
    assert generation.status_code == 201
    return project_id, generation.json()["id"]


def test_three_reviewer_runs_are_isolated_and_grouped_with_sources(client) -> None:
    project_id, generation_id = _create_generation(client)
    response = client.post(f"/api/projects/{project_id}/case-generations/{generation_id}/reviews", json={})
    assert response.status_code == 201
    batch = response.json()
    assert batch["status"] == "completed"
    assert {run["role"] for run in batch["reviewer_runs"]} == {
        "product_manager", "test_manager", "project_manager",
    }
    assert all("suggestions" not in run["input_context"] for run in batch["reviewer_runs"])
    assert batch["groups"][0]["source_roles"] == ["product_manager", "test_manager", "project_manager"]
    ai_runs = client.get(f"/api/projects/{project_id}/ai-runs").json()
    review_runs = [run for run in ai_runs if run["task_type"] == "case_review"]
    assert len(review_runs) == 3
    assert {run["prompt_version"] for run in review_runs} == {
        "case-review.v1.product_manager", "case-review.v1.test_manager", "case-review.v1.project_manager",
    }


def test_disposition_creates_immutable_revision_and_confirmation_gate(client) -> None:
    project_id, generation_id = _create_generation(client)
    batch = client.post(f"/api/projects/{project_id}/case-generations/{generation_id}/reviews", json={}).json()
    candidate_id = batch["suggestions"][0]["candidate_id"]
    confirm_url = f"/api/projects/{project_id}/case-review-batches/{batch['id']}/confirm"
    blocked = client.post(confirm_url, json={"confirmer_name": "测试工程师", "inclusion": {candidate_id: True}})
    assert blocked.status_code == 409

    for index, suggestion in enumerate(batch["suggestions"]):
        response = client.patch(
            f"/api/projects/{project_id}/case-review-batches/{batch['id']}/suggestions/{suggestion['id']}",
            json={
                "decision": "modified" if index == 0 else "accepted",
                "reason": "保留可追踪的人工处置理由",
                "modified_fields": {"title": "测试工程师修改后的用例标题"} if index == 0 else {},
            },
        )
        assert response.status_code == 200
    revised = client.get(f"/api/projects/{project_id}/case-review-batches/{batch['id']}").json()
    assert len(revised["revisions"]) == len(batch["suggestions"])
    assert revised["revisions"][0]["candidate"]["title"] == "测试工程师修改后的用例标题"
    confirmed_response = client.post(
        confirm_url, json={"confirmer_name": "测试工程师", "inclusion": {candidate_id: True}},
    )
    assert confirmed_response.status_code == 200
    confirmed = client.get(f"/api/projects/{project_id}/case-review-batches/{batch['id']}").json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmed_by"] == "测试工程师"
    assert confirmed["revisions"][-1]["stable_case_id"].startswith("case-")
    history = client.get(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/history",
    ).json()
    assert history[-1]["event_type"] == "case_confirmed"
