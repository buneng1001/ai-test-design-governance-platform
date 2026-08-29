import base64

from fastapi.testclient import TestClient


def _setup(
    client: TestClient, template_field: str = "title", template_filename: str = "用例.csv",
    template_content: str | None = None,
) -> tuple[int, int, int]:
    project = client.post(
        "/api/projects",
        json={"name": "候选用例项目", "test_object": "虚构智能采集设备", "software_version": "v1.0.0", "description": "生成测试用例"},
    ).json()
    content = base64.b64encode("设备必须保存状态。\n".encode()).decode()
    asset = client.post(f"/api/projects/{project['id']}/assets", json={
        "name": "requirements.md", "asset_type": "requirement_material", "provenance_kind": "original_synthetic",
        "source": "测试工程师从零创作", "usage_permission": "project_owned", "model_permission": "allowed",
        "requirement_version": "V1", "purpose": "需求评审", "content_base64": content, "change_reason": "首次登记",
    }).json()
    package = client.post(f"/api/projects/{project['id']}/requirement-packages", json={
        "name": "V1 需求资料包", "files": [{
            "asset_id": asset["id"], "filename": "requirements.md", "media_type": "text/markdown",
            "content_base64": content,
        }],
    }).json()
    version = client.post(f"/api/projects/{project['id']}/requirement-packages/{package['id']}/publish").json()
    analysis = client.post(
        f"/api/projects/{project['id']}/requirement-versions/{version['id']}/requirement-review"
    ).json()
    for candidate in analysis["atomic_requirements"]:
        client.patch(
            f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}"
            f"/atomic-requirements/{candidate['candidate_id']}", json={"decision": "accepted"}
        )
    for finding in analysis["findings"]:
        client.patch(
            f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/findings/{finding['finding_id']}",
            json={"status": "resolved"},
        )
    client.post(
        f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    design = client.post(
        f"/api/projects/{project['id']}/requirement-versions/{version['id']}/test-designs", json={}
    ).json()
    client.post(
        f"/api/projects/{project['id']}/test-designs/{design['id']}/confirm", json={"confirmer_name": "测试工程师"}
    )
    headers = (
        "用例标题,测试步骤,预期结果,设计依据\n"
        if template_field == "design_basis" else "用例标题,测试步骤,预期结果\n"
    )
    csv = template_content or base64.b64encode(headers.encode()).decode()
    mapping = client.post(
        f"/api/projects/{project['id']}/template-mappings",
        json={"filename": template_filename, "content_base64": csv},
    ).json()
    sheets = mapping["sheets"]
    field_mapping = {"用例标题": "title", "测试步骤": "steps", "预期结果": "overall_expectation"}
    if template_filename.endswith(".xlsx"):
        field_mapping = {"用例编号": "external_case_number", "用例标题": "title",
                          "测试步骤": "steps", "预期结果": "overall_expectation"}
    if template_field == "design_basis":
        field_mapping["设计依据"] = template_field
    sheets[0].update({"role": "case", "participates": True, "title_row": 1, "field_mapping": field_mapping})
    client.post(
        f"/api/projects/{project['id']}/template-mappings/{mapping['id']}/confirm",
        json={"confirmer_name": "测试工程师", "mappings": [
            {
                "sheet_name": sheets[0]["name"], "role": "case", "participates": True, "title_row": 1,
                "field_mapping": sheets[0]["field_mapping"],
            },
            *[
                {"sheet_name": sheet["name"], "role": "instruction", "participates": False,
                 "title_row": sheet["title_row"], "field_mapping": {}}
                for sheet in sheets[1:]
            ],
        ]},
    )
    return project["id"], design["id"], mapping["id"]


def test_generation_keeps_traceability_granularity_and_internal_basis(client: TestClient) -> None:
    project_id, design_id, mapping_id = _setup(client)
    response = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal", "boundary"]},
    )
    assert response.status_code == 201
    generation = response.json()
    assert generation["status"] == "succeeded"
    assert len(generation["candidates"]) == 2
    first = generation["candidates"][0]
    assert first["requirement_ids"] and first["requirement_references"]
    assert first["scope_item_id"] and first["risk_item_id"] and first["priority"]
    assert first["steps"][0]["expected"] and first["overall_expectation"]
    assert first["design_basis"]
    assert "design_basis" not in {"title", "steps", "overall_expectation"}
    assert first["automation_mapping"] == generation["candidates"][1]["automation_mapping"]
    assert client.get(f"/api/projects/{project_id}/case-generations/{generation['id']}").status_code == 200


def test_template_limitation_requires_explicit_confirmation(client: TestClient) -> None:
    project_id, design_id, mapping_id = _setup(client, template_field="design_basis")
    blocked = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id},
    )
    assert blocked.status_code == 409
    assert "template_limitations" in blocked.text
    accepted = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "accept_template_limitations": True, "variants": ["normal"]},
    )
    assert accepted.status_code == 201
    assert accepted.json()["candidates"][0]["unexpressed_fields"] == ["unsupported_semantics"]


def test_invalid_or_unconfirmed_ai_output_never_creates_candidates(client: TestClient) -> None:
    project_id, design_id, mapping_id = _setup(client)
    for scenario, expected_status in (("invalid_schema", 422), ("missing_source", 422), ("timeout", 503)):
        response = client.post(
            f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
            json={"template_mapping_id": mapping_id, "scenario": scenario, "max_retries": 1},
        )
        assert response.status_code == expected_status
    assert client.get(f"/api/projects/{project_id}/case-generations").json() == []
    audit = client.get(f"/api/projects/{project_id}/ai-runs").json()
    case_runs = [run for run in audit if run["task_type"] == "case_generation"]
    assert len(case_runs) == 3
