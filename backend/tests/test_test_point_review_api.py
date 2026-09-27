from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.requirement_schemas import SourceReference
from app.test_point_review_schemas import ReviewTestItem, ReviewTestPoint
from app.test_point_review_service import calculate_coverage
from test_test_design_api import _setup_confirmed_version


def _analysis_id(client: TestClient, project_id: int) -> int:
    workflow = client.get(f"/api/projects/{project_id}/workflow").json()
    return workflow["asset_ids"]["requirement_analysis_id"]


def _prepare_review(client: TestClient) -> tuple[int, int, int, dict]:
    project_id, version_id = _setup_confirmed_version(client)
    analysis_id = _analysis_id(client, project_id)
    suggestions = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/suggestions/generate"
    ).json()
    return project_id, version_id, analysis_id, suggestions


def test_test_point_review_keeps_stable_traceability_and_excludes_unresolved_suggestion_scope(client: TestClient) -> None:
    project_id, _, analysis_id, suggestions = _prepare_review(client)
    pending_requirement_id = suggestions["suggestions"][0]["related_requirement_ids"][0]
    assert client.patch(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/suggestions/"
        f"{suggestions['suggestions'][0]['suggestion_id']}",
        json={"disposition": "awaiting_external_confirmation"},
    ).status_code == 200
    generated = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review"
    )

    assert generated.status_code == 200
    review = generated.json()["test_point_review"]
    assert review["coverage_check"]["passed"] is True
    assert all(point["skill_test_point_id"].startswith("S07-TP-") for point in review["test_points"])
    assert len({point["platform_test_point_id"] for point in review["test_points"]}) == len(review["test_points"])
    analysis = client.get(f"/api/projects/{project_id}/requirement-reviews/{analysis_id}").json()
    stable_by_candidate = {item["candidate_id"]: item["stable_requirement_id"] for item in analysis["atomic_requirements"]}
    assert stable_by_candidate[pending_requirement_id] not in {
        requirement_id for point in review["test_points"] for requirement_id in point["stable_requirement_ids"]
    }
    assert all("步骤" not in point["objective"] and "预期结果" not in point["objective"] for point in review["test_points"])
    exported = client.get(f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/step-00-08-package.md")
    assert exported.status_code == 200
    assert "## Step 07 测试项与测试点" in exported.text


def test_confirmed_selection_is_the_only_case_generation_scope(client: TestClient) -> None:
    project_id, version_id, analysis_id, suggestions = _prepare_review(client)
    for suggestion in suggestions["suggestions"]:
        assert client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/suggestions/{suggestion['suggestion_id']}",
            json={"disposition": "rejected"},
        ).status_code == 200
    review = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review"
    ).json()["test_point_review"]
    selected = next(point for point in review["test_points"] if point["direction"] == "normal")
    assert client.patch(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review/selection",
        json={"test_point_ids": [selected["platform_test_point_id"]]},
    ).status_code == 200
    confirmed = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["test_point_review"]["handoff_version"]

    design = client.post(f"/api/projects/{project_id}/requirement-versions/{version_id}/test-designs", json={}).json()
    assert client.post(
        f"/api/projects/{project_id}/test-designs/{design['id']}/confirm", json={"confirmer_name": "测试工程师"},
    ).status_code == 200
    generated = client.post(
        f"/api/projects/{project_id}/test-designs/{design['id']}/case-generations",
        json={"variants": ["normal", "boundary"]},
    )
    assert generated.status_code == 201
    assert [item["platform_test_point_id"] for item in generated.json()["candidates"]] == [selected["platform_test_point_id"]]


def test_empty_confirmed_scope_cannot_enter_case_generation(client: TestClient) -> None:
    project_id, version_id, analysis_id, suggestions = _prepare_review(client)
    for suggestion in suggestions["suggestions"]:
        client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/suggestions/{suggestion['suggestion_id']}",
            json={"disposition": "rejected"},
        )
    assert client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review"
    ).status_code == 200
    assert client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review/confirm",
        json={"confirmer_name": "测试工程师"},
    ).status_code == 200
    design = client.post(f"/api/projects/{project_id}/requirement-versions/{version_id}/test-designs", json={}).json()
    client.post(f"/api/projects/{project_id}/test-designs/{design['id']}/confirm", json={"confirmer_name": "测试工程师"})
    blocked = client.post(f"/api/projects/{project_id}/test-designs/{design['id']}/case-generations", json={})
    assert blocked.status_code == 409
    assert "未选择测试点范围" in blocked.json()["detail"]


def test_selected_risk_point_is_generated_even_when_legacy_variants_omit_scenario(client: TestClient) -> None:
    project_id, version_id, analysis_id, suggestions = _prepare_review(client)
    for suggestion in suggestions["suggestions"]:
        client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/suggestions/{suggestion['suggestion_id']}",
            json={"disposition": "rejected"},
        )
    review = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review"
    ).json()["test_point_review"]
    risk_point = next(point for point in review["test_points"] if point["direction"] == "risk")
    client.patch(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review/selection",
        json={"test_point_ids": [risk_point["platform_test_point_id"]]},
    )
    client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis_id}/test-point-review/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    design = client.post(f"/api/projects/{project_id}/requirement-versions/{version_id}/test-designs", json={}).json()
    client.post(f"/api/projects/{project_id}/test-designs/{design['id']}/confirm", json={"confirmer_name": "测试工程师"})
    generated = client.post(
        f"/api/projects/{project_id}/test-designs/{design['id']}/case-generations",
        json={"variants": ["normal"]},
    )

    assert generated.status_code == 201
    assert generated.json()["candidates"][0]["platform_test_point_id"] == risk_point["platform_test_point_id"]
    assert generated.json()["candidates"][0]["variant"] == "scenario"


def test_coverage_check_deterministically_reports_missing_and_isolated_relations() -> None:
    source = SourceReference(reference_id="ref-1", asset_id=1, filename="SRS.md", locator="L1")
    item = ReviewTestItem(
        test_item_id="item-1", name="状态保存", module="状态", stable_requirement_ids=["REQ-1"],
        source_references=[source],
    )
    isolated_point = ReviewTestPoint(
        skill_test_point_id="S07-TP-001", platform_test_point_id="point-1", test_item_id="missing-item",
        stable_requirement_ids=["REQ-2"], source_references=[source], direction="normal", objective="验证状态保存",
    )
    coverage = calculate_coverage(
        [SimpleNamespace(stable_requirement_id="REQ-1"), SimpleNamespace(stable_requirement_id="REQ-2")],
        [item], [isolated_point],
    )

    assert coverage.passed is False
    assert coverage.uncovered_requirement_ids == ["REQ-1"]
    assert coverage.isolated_test_point_ids == ["point-1"]
    assert coverage.direction_gaps["item-1"] == ["normal", "exception", "boundary", "risk"]
