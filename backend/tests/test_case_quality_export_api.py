import csv
import io
import zipfile
import base64

from test_case_generation_api import _setup
from app.template_service import _xlsx_rows, _xlsx_sheets


def _confirmed_batch(client):
    project_id, design_id, mapping_id = _setup(client)
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal", "boundary"]},
    ).json()
    batch = client.post(f"/api/projects/{project_id}/case-generations/{generation['id']}/reviews", json={}).json()
    for suggestion in batch["suggestions"]:
        client.patch(
            f"/api/projects/{project_id}/case-review-batches/{batch['id']}/suggestions/{suggestion['id']}",
            json={"decision": "accepted", "reason": "测试工程师确认"},
        )
    confirmed = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/confirm",
        json={"confirmer_name": "测试工程师", "inclusion": {
            item["candidate_id"]: True for item in batch["suggestions"]}},
    ).json()
    return project_id, confirmed


def test_quality_checks_and_standard_exports_are_deterministic_and_selection_safe(client) -> None:
    project_id, batch = _confirmed_batch(client)
    batch_id = batch["id"]
    chosen_id = batch["revisions"][-1]["stable_case_id"]

    checks = client.get(f"/api/projects/{project_id}/case-review-batches/{batch_id}/quality-checks")
    assert checks.status_code == 200, checks.text
    report = checks.json()
    assert report["coverage"]["requirements"]["denominator"] >= 1
    assert report["coverage"]["test_points"]["denominator"] >= 1
    assert all(item["rule"] != "ai_suggestion" for item in report["issues"])

    preview = client.get(f"/api/projects/{project_id}/case-review-batches/{batch_id}/standard-preview")
    assert preview.status_code == 200
    assert preview.json()["columns"] == [
        "stable_case_id", "external_case_number", "title", "objective", "priority", "software_version", "preconditions", "steps", "step_expectations",
        "overall_expectation", "evidence_requirements", "design_basis", "traceability", "source",
    ]
    assert chosen_id in {row["stable_case_id"] for row in preview.json()["rows"]}

    xlsx = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch_id}/standard-export",
        json={"scope": "selected", "stable_case_ids": [chosen_id], "format": "xlsx"},
    )
    assert xlsx.status_code == 200
    with zipfile.ZipFile(io.BytesIO(xlsx.content)) as workbook:
        sheet = next(path for name, path in _xlsx_sheets(workbook) if name == "平台标准用例表")
        rows = _xlsx_rows(workbook, sheet)
    assert rows[0][0] == "stable_case_id"
    assert [row[0] for row in rows[1:]] == [chosen_id]
    assert "\n\n" not in rows[1][7]
    assert rows[1][5] == "v1.0.0"

    exported_csv = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch_id}/standard-export",
        json={"scope": "selected", "stable_case_ids": [chosen_id], "format": "csv"},
    )
    rows = list(csv.DictReader(io.StringIO(exported_csv.content.decode("utf-8-sig"))))
    assert [row["stable_case_id"] for row in rows] == [chosen_id]
    assert rows[0]["source"] == "standard"


def test_unconfirmed_custom_template_falls_back_without_blocking_case_review(client) -> None:
    project_id, design_id, _ = _setup(client)
    uploaded = client.post(f"/api/projects/{project_id}/template-mappings", json={
        "filename": "incomplete.csv", "content_base64": base64.b64encode("未知列\n".encode()).decode(),
    }).json()
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": uploaded["id"], "variants": ["normal"]},
    )
    assert generation.status_code == 201, generation.text
    payload = generation.json()
    assert any(item["code"] == "template_mapping_fallback" for item in payload["template_diagnostics"])
    assert all(item["template_fallback"] for item in payload["candidates"])
    preview = client.get(f"/api/projects/{project_id}/case-generations/{payload['id']}/standard-preview")
    assert preview.status_code == 200
    assert preview.json()["rows"][0]["source"] == "template_fallback"
    assert client.get(f"/api/projects/{project_id}/case-generations/{payload['id']}/quality-checks").status_code == 200
    fallback_export = client.post(f"/api/projects/{project_id}/case-generations/{payload['id']}/standard-export",
                                  json={"format": "csv"})
    assert fallback_export.status_code == 200
    assert "template_fallback" in fallback_export.content.decode("utf-8-sig")
    assert client.post(f"/api/projects/{project_id}/case-generations/{payload['id']}/reviews", json={}).status_code == 201
