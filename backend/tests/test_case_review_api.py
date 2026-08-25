import io
import zipfile

from test_case_generation_api import _setup
from test_template_mapping_api import _xlsx
from app.template_service import _xlsx_sheets


def _create_generation(
    client, template_filename: str = "用例.csv", template_content: str | None = None,
) -> tuple[int, int]:
    project_id, design_id, mapping_id = _setup(client, template_filename=template_filename,
                                                template_content=template_content)
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


def test_case_lifecycle_and_template_export_keep_public_fields_only(client) -> None:
    project_id, generation_id = _create_generation(client)
    batch = client.post(f"/api/projects/{project_id}/case-generations/{generation_id}/reviews", json={}).json()
    for suggestion in batch["suggestions"]:
        client.patch(
            f"/api/projects/{project_id}/case-review-batches/{batch['id']}/suggestions/{suggestion['id']}",
            json={"decision": "accepted", "reason": "测试工程师确认建议"},
        )
    candidate_id = batch["suggestions"][0]["candidate_id"]
    confirmed = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/confirm",
        json={"confirmer_name": "测试工程师", "inclusion": {candidate_id: True}},
    ).json()
    revision = confirmed["revisions"][-1]
    assert revision["stable_case_id"]
    assert revision["lifecycle_status"] == "effective"
    assert revision["participation_status"] == "included"

    export = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/export",
        json={"scope": "all"},
    )
    assert export.status_code == 200
    assert "text/csv" in export.headers["content-type"]
    assert "设计依据" not in export.text
    assert "AI" not in export.text
    assert "任务" not in export.text

    updated = client.patch(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/cases/{revision['stable_case_id']}/status",
        json={
            "lifecycle_status": "closed", "participation_status": "not_included",
            "reason": "当前测试不再需要", "confirmer_name": "测试工程师",
        },
    )
    assert updated.status_code == 200
    current = next(item for item in updated.json()["revisions"]
                   if item["stable_case_id"] == revision["stable_case_id"] and item["revision"] == revision["revision"])
    assert current["lifecycle_status"] == "closed"
    change = updated.json()["status_changes"][-1]
    assert change["previous_lifecycle_status"] == "effective"
    assert change["lifecycle_status"] == "closed"
    assert change["reason"] == "当前测试不再需要"
    assert change["confirmer_name"] == "测试工程师"
    assert client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/export", json={"scope": "all"},
    ).content.count(b"\n") == 1


def test_case_export_round_trips_xlsx_sheets(client) -> None:
    project_id, generation_id = _create_generation(
        client, template_filename="用例模板.xlsx", template_content=_xlsx(),
    )
    batch = client.post(f"/api/projects/{project_id}/case-generations/{generation_id}/reviews", json={}).json()
    for suggestion in batch["suggestions"]:
        client.patch(
            f"/api/projects/{project_id}/case-review-batches/{batch['id']}/suggestions/{suggestion['id']}",
            json={"decision": "accepted", "reason": "测试工程师确认建议"},
        )
    candidate_id = batch["suggestions"][0]["candidate_id"]
    confirmed = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/confirm",
        json={"confirmer_name": "测试工程师", "inclusion": {candidate_id: True}},
    )
    stable_case_id = confirmed.json()["revisions"][-1]["stable_case_id"]
    exported = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/export", json={"scope": "all"},
    )
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert {"用例", "说明"} == {
            sheet[0] for sheet in _xlsx_sheets(archive)
        }
    assert stable_case_id
