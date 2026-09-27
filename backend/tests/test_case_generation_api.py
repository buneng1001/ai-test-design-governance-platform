import base64
import io
import zipfile

from fastapi.testclient import TestClient
from app.ai_service import ModelResponse, MockModelService, OpenAICompatibleModelService


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
    suggestions = client.post(
        f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/suggestions/generate"
    ).json()
    for suggestion in suggestions["suggestions"]:
        client.patch(
            f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}"
            f"/suggestions/{suggestion['suggestion_id']}", json={"disposition": "rejected"},
        )
    review = client.post(
        f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/test-point-review"
    ).json()["test_point_review"]
    client.patch(
        f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/test-point-review/selection",
        json={"test_item_ids": [item["test_item_id"] for item in review["test_items"]]},
    )
    client.post(
        f"/api/projects/{project['id']}/requirement-reviews/{analysis['id']}/test-point-review/confirm",
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
    assert len(generation["candidates"]) == 4
    first = generation["candidates"][0]
    assert first["requirement_ids"] and first["requirement_references"]
    assert first["scope_item_id"] and first["risk_item_id"] and first["priority"]
    assert first["steps"][0]["expected"] and first["overall_expectation"]
    assert first["design_basis"]
    assert "design_basis" not in {"title", "steps", "overall_expectation"}
    assert first["automation_mapping"] == generation["candidates"][1]["automation_mapping"]
    assert client.get(f"/api/projects/{project_id}/case-generations/{generation['id']}").status_code == 200


def test_generation_preserves_structured_model_case_content(client: TestClient, monkeypatch) -> None:
    project_id, design_id, mapping_id = _setup(client)
    captured_context = {}

    def complete(_: MockModelService, request) -> ModelResponse:
        point = request.input_context[0]
        captured_context.update(point)
        return ModelResponse(raw_output={
            "contract_version": "case-generation.v1",
            "items": [{
                "test_point_id": point["platform_test_point_id"],
                "variant": "boundary",
                "case_discriminator": "maximum-allowed-value",
                "title": "模型给出的保存上限边界",
                "objective": "验证保存输入达到上限时的可观察行为",
                "preconditions": ["设备已连接", "存储空间充足"],
                "steps": [{
                    "order": 1, "action": "输入最大允许值", "input": "最大边界值",
                    "expected": "界面允许提交",
                }, {
                    "order": 2, "action": "提交保存", "input": "点击保存",
                    "expected": "返回保存成功提示",
                }],
                "overall_expectation": "保存后的状态与最大允许输入一致。",
                "evidence_requirements": ["保存请求与响应", "保存后状态截图"],
                "design_basis": [{
                    "method": "boundary", "reason": "最大允许值是独立边界场景。",
                }],
                "pending_confirmations": ["最大允许值的具体数值待产品确认"],
            }],
        })

    monkeypatch.setattr(MockModelService, "complete", complete)
    response = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal", "boundary"]},
    )

    assert response.status_code == 201
    candidate = response.json()["candidates"][0]
    assert candidate["title"] == "模型给出的保存上限边界"
    assert candidate["objective"] == "验证保存输入达到上限时的可观察行为"
    assert candidate["steps"][1]["expected"] == "返回保存成功提示"
    assert candidate["pending_confirmations"] == ["最大允许值的具体数值待产品确认"]
    assert captured_context["rules"]


def test_generation_rejects_model_case_outside_selected_test_points(client: TestClient, monkeypatch) -> None:
    project_id, design_id, mapping_id = _setup(client)

    def complete(_: MockModelService, request) -> ModelResponse:
        return ModelResponse(raw_output={
            "contract_version": "case-generation.v1",
            "items": [{
                "test_point_id": "point-not-selected", "variant": "normal", "case_discriminator": "outside-scope", "title": "越界用例",
                "objective": "不应保存", "preconditions": ["无"],
                "steps": [{"order": 1, "action": "执行", "input": "输入", "expected": "结果"}],
                "overall_expectation": "不应进入候选", "evidence_requirements": ["日志"],
                "design_basis": [{"method": "scenario", "reason": "越界检查"}],
                "pending_confirmations": [],
            }],
        })

    monkeypatch.setattr(MockModelService, "complete", complete)
    response = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id},
    )

    assert response.status_code == 422
    assert client.get(f"/api/projects/{project_id}/case-generations").json() == []


def test_generation_rejects_unmarked_uncertainty_as_candidate_fact(client: TestClient, monkeypatch) -> None:
    project_id, design_id, mapping_id = _setup(client)

    def complete(_: MockModelService, request) -> ModelResponse:
        point = request.input_context[0]
        return ModelResponse(raw_output={
            "contract_version": "case-generation.v1",
            "items": [{
                "test_point_id": point["platform_test_point_id"], "variant": "normal",
                "case_discriminator": "unconfirmed-threshold", "title": "阈值行为", "objective": "验证阈值",
                "preconditions": ["设备已连接"],
                "steps": [{"order": 1, "action": "输入阈值", "input": "待确认阈值", "expected": "系统响应"}],
                "overall_expectation": "系统符合规则", "evidence_requirements": ["日志"],
                "design_basis": [{"method": "scenario", "reason": "阈值场景"}], "pending_confirmations": [],
            }],
        })

    monkeypatch.setattr(MockModelService, "complete", complete)
    response = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id},
    )

    assert response.status_code == 422
    assert client.get(f"/api/projects/{project_id}/case-generations").json() == []


def test_generation_distinguishes_boundary_candidates_by_deterministic_key(client: TestClient, monkeypatch) -> None:
    project_id, design_id, mapping_id = _setup(client)

    def complete(_: MockModelService, request) -> ModelResponse:
        point = request.input_context[0]
        def item(discriminator: str, title: str) -> dict:
            return {
                "test_point_id": point["platform_test_point_id"], "variant": "boundary",
                "case_discriminator": discriminator, "title": title, "objective": "验证保存上限边界",
                "preconditions": ["设备已连接"],
                "steps": [{"order": 1, "action": "输入边界值", "input": discriminator, "expected": "允许保存"}],
                "overall_expectation": "系统行为符合确认规则", "evidence_requirements": ["请求响应"],
                "design_basis": [{"method": "boundary", "reason": "独立边界值"}], "pending_confirmations": [],
            }
        return ModelResponse(raw_output={"contract_version": "case-generation.v1", "items": [
            item("maximum-allowed", "最大允许值"), item("just-above-maximum", "超过最大值"),
        ]})

    monkeypatch.setattr(MockModelService, "complete", complete)
    response = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["boundary"]},
    )

    assert response.status_code == 201
    candidates = response.json()["candidates"]
    assert [item["title"] for item in candidates] == ["最大允许值", "超过最大值"]
    assert len({item["candidate_key"] for item in candidates}) == 2
    assert len({item["id"] for item in candidates}) == 2


def test_candidate_edit_removal_and_restore_are_persisted_with_original_content(client: TestClient) -> None:
    project_id, design_id, mapping_id = _setup(client)
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal"]},
    ).json()
    candidate = generation["candidates"][0]
    edited = client.patch(
        f"/api/projects/{project_id}/case-generations/{generation['id']}/candidates/{candidate['id']}",
        json={"title": "人工编辑后的候选标题", "reason": "补充可读性"},
    )
    assert edited.status_code == 200
    removed = client.patch(
        f"/api/projects/{project_id}/case-generations/{generation['id']}/candidates/{candidate['id']}/removal",
        json={"removed": True, "reason": "本次不纳入"},
    )
    assert removed.status_code == 200
    restored = client.patch(
        f"/api/projects/{project_id}/case-generations/{generation['id']}/candidates/{candidate['id']}/removal",
        json={"removed": False, "reason": "重新纳入审核"},
    )
    assert restored.status_code == 200
    persisted = client.get(f"/api/projects/{project_id}/case-generations/{generation['id']}").json()
    assert persisted["candidates"][0]["title"] == "人工编辑后的候选标题"
    assert persisted["original_candidates"][0]["title"] == candidate["title"]
    assert persisted["removed_candidate_ids"] == []
    assert [item["action"] for item in persisted["candidate_history"]] == ["edited", "removed", "restored"]


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


def test_real_case_generation_uses_session_model(client: TestClient, monkeypatch) -> None:
    project_id, design_id, mapping_id = _setup(client)

    def complete(_: OpenAICompatibleModelService, request) -> ModelResponse:
        assert request.model_parameters.provider == "custom"
        return ModelResponse(raw_output={"contract_version": "case-generation.v1", "items": []})

    monkeypatch.setattr(OpenAICompatibleModelService, "complete", complete)
    config = client.put("/api/ai-session-config", headers={"X-Session-ID": "real-case-test"}, json={
        "provider": "custom", "model": "test-model", "base_url": "https://example.invalid", "api_key": "secret",
    })
    assert config.status_code == 200 and "secret" not in config.text
    response = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        headers={"X-Session-ID": "real-case-test"},
        json={"template_mapping_id": mapping_id, "mode": "real", "variants": ["normal"]},
    )
    assert response.status_code == 201
    assert response.json()["is_mock"] is False


def test_default_template_is_xlsx_with_sixteen_columns(client: TestClient) -> None:
    project_id, design_id, _ = _setup(client)
    response = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"variants": ["normal"]},
    )
    assert response.status_code == 201
    mapping_id = response.json()["template_mapping_id"]
    exported = client.get(f"/api/projects/{project_id}/template-mappings/{mapping_id}/export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as workbook:
        sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert sheet.count("<c ") == 16
    assert "父记录" not in sheet
