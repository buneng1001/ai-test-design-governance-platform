import base64
import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.ai_service import ModelResponse
from app.main import create_app
from app.v020_export import _case_xlsx


def _project_and_material(client: TestClient) -> int:
    project = client.post("/api/projects", json={
        "name": "AI 工作流项目", "test_object": "智能终端", "software_version": "v0.2.0",
        "description": "", "settings": {"requirement_language": "zh-CN"},
    }).json()
    response = client.post(f"/api/v0.2/projects/{project['id']}/materials", json={
        "supplemental_notes": "重点关注状态切换和异常提示。",
        "files": [{
            "filename": "requirements.md", "media_type": "text/markdown",
            "content_base64": base64.b64encode(
                "# 状态管理\n设备必须在 2 秒内完成状态切换。\n异常时必须显示错误提示。".encode()
            ).decode(),
        }],
    })
    assert response.status_code == 201
    return project["id"]


def test_local_analysis_persists_run_evidence_and_cross_page_selection(client: TestClient) -> None:
    project_id = _project_and_material(client)
    preflight = client.post(f"/api/v0.2/projects/{project_id}/run-preflight", json={
        "page": "analysis", "mode": "local",
    })
    assert preflight.status_code == 200
    estimate = preflight.json()
    assert estimate["input_summary"]["file_count"] == 1
    assert estimate["input_summary"]["fragment_count"] == 3
    assert estimate["estimated_input_tokens"] > 0
    assert estimate["estimated_cost"]["status"] == "unavailable"

    response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    })
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["run"]["status"] == "completed"
    assert result["run"]["mode"] == "local"
    assert result["run"]["source_label"] == "本地模拟（未调用 AI）"
    assert [event["stage"] for event in result["run"]["stage_events"]] == [
        "准备输入", "调用模型", "校验输出", "保存结果", "完成",
    ]
    assert result["run"]["actual_usage"]["status"] == "unavailable"
    assert result["rows"] and all(item["selected"] is False for item in result["rows"])

    selected_id = result["rows"][0]["id"]
    selection = client.patch(f"/api/v0.2/projects/{project_id}/analysis-selection", json={
        "row_ids": [selected_id], "selected": True,
    })
    assert selection.status_code == 200
    assert selection.json()["selected_count"] == 1
    restored = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()
    assert next(item for item in restored["analysis_rows"] if item["id"] == selected_id)["selected"] is True


def test_suggestions_and_role_review_flow_back_unselected(client: TestClient) -> None:
    project_id = _project_and_material(client)
    analysis = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    }).json()
    first_id = analysis["rows"][0]["id"]
    client.patch(f"/api/v0.2/projects/{project_id}/analysis-selection", json={
        "row_ids": [first_id], "selected": True,
    })

    suggestions = client.post(f"/api/v0.2/projects/{project_id}/suggestion-runs", json={
        "mode": "local", "confirmed": True,
    })
    assert suggestions.status_code == 201
    suggestion = suggestions.json()["suggestions"][0]
    accepted = client.patch(
        f"/api/v0.2/projects/{project_id}/suggestions/{suggestion['id']}", json={"disposition": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["analysis_row"]["selected"] is False
    assert accepted.json()["analysis_row"]["origin"] == "suggestion"

    reviewed = client.post(f"/api/v0.2/projects/{project_id}/review-runs", json={
        "mode": "local", "confirmed": True, "roles": ["product_manager", "test_manager"],
    })
    assert reviewed.status_code == 201
    assert {item["role"] for item in reviewed.json()["suggestions"]} == {"product_manager", "test_manager"}
    review_item = reviewed.json()["suggestions"][0]
    accepted_review = client.patch(
        f"/api/v0.2/projects/{project_id}/review-suggestions/{review_item['id']}",
        json={"disposition": "accepted"},
    )
    assert accepted_review.status_code == 200
    assert accepted_review.json()["analysis_row"]["selected"] is False
    assert accepted_review.json()["analysis_row"]["origin"] == "review"
    assert client.post(f"/api/v0.2/projects/{project_id}/review-skip").status_code == 200


def test_case_generation_uses_only_selected_rows_and_supports_editing(client: TestClient) -> None:
    project_id = _project_and_material(client)
    rows = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    }).json()["rows"]
    assert client.post(f"/api/v0.2/projects/{project_id}/case-runs", json={
        "mode": "local", "confirmed": True, "template_mode": "default",
        "supplemental_requirements": "优先生成 P1。",
    }).status_code == 409

    selected_ids = [rows[0]["id"], rows[-1]["id"]]
    client.patch(f"/api/v0.2/projects/{project_id}/analysis-selection", json={
        "row_ids": selected_ids, "selected": True,
    })
    preflight = client.post(f"/api/v0.2/projects/{project_id}/run-preflight", json={
        "page": "cases", "mode": "local", "template_mode": "default",
        "supplemental_requirements": "优先生成 P1。",
    }).json()
    assert preflight["template_filename"] == "默认测试用例模板.xlsx"
    assert preflight["supplemental_requirements"] == "优先生成 P1。"
    generated = client.post(f"/api/v0.2/projects/{project_id}/case-runs", json={
        "mode": "local", "confirmed": True, "template_mode": "default",
        "supplemental_requirements": "优先生成 P1。",
    })
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["template"]["filename"] == "默认测试用例模板.xlsx"
    assert body["scope_ids"] == selected_ids
    assert {item["analysis_row_id"] for item in body["cases"]} == set(selected_ids)

    case_id = body["cases"][0]["id"]
    edited = client.patch(f"/api/v0.2/projects/{project_id}/cases/{case_id}", json={
        "title": "人工编辑后的标题", "priority": "P0",
    })
    assert edited.status_code == 200
    assert edited.json()["title"] == "人工编辑后的标题"
    excluded = client.patch(f"/api/v0.2/projects/{project_id}/cases/{case_id}/inclusion", json={
        "included": False,
    })
    assert excluded.json()["included"] is False

    template = client.get(f"/api/v0.2/projects/{project_id}/case-template")
    assert template.json()["mapping"]["sheets"][0]["field_mapping"]["测试用例标题"] == "title"
    exported_json = client.get(f"/api/v0.2/projects/{project_id}/exports/cases?format=json")
    assert exported_json.status_code == 200
    assert exported_json.json()["items"][0]["analysis_row_id"] in selected_ids
    exported_xlsx = client.get(f"/api/v0.2/projects/{project_id}/exports/cases?format=xlsx")
    assert exported_xlsx.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported_xlsx.content)) as workbook:
        assert "xl/worksheets/sheet1.xml" in workbook.namelist()
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "人工编辑后的标题" not in sheet_xml
    assert len(client.get(f"/api/v0.2/projects/{project_id}/workspace").json()["exports"]) == 2
    exact_export = client.get(
        f"/api/v0.2/projects/{project_id}/exports/cases?format=json&run_id={body['run']['id']}"
    )
    assert exact_export.json()["run_id"] == body["run"]["id"]
    restored = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()
    assert restored["case_generations"][0]["scope_ids"] == selected_ids
    assert restored["exports"][-1]["record_id"] == body["run"]["id"]


def test_real_mode_is_blocked_until_existing_model_config_is_verified(client: TestClient) -> None:
    project_id = _project_and_material(client)
    response = client.post(f"/api/v0.2/projects/{project_id}/run-preflight", json={
        "page": "analysis", "mode": "skill",
    })
    assert response.status_code == 409
    assert "打开已有模型配置" in response.json()["detail"]


class CaptureModelService:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        return ModelResponse(raw_output={"rows": [{
            "module": "状态管理", "function_point": "状态切换", "test_item": "时延验证",
            "test_point": "验证状态切换耗时", "source_reference_id": "input-1",
            "ai_reason": "约束包含明确时限", "information_gap": "", "status": "ready",
        }]}, input_tokens=120, output_tokens=80, total_tokens=200)


def test_direct_and_skill_use_same_scope_but_distinct_versioned_prompts(tmp_path: Path, monkeypatch) -> None:
    service = CaptureModelService()
    application = create_app(
        tmp_path / "v020-ai.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_and_material(client)
        headers = {"X-Session-ID": "v020-ai-client"}
        config = {
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        }
        assert client.post("/api/ai-session-config/test", headers=headers, json=config).json()["success"] is True
        direct = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })
        skill = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert direct.status_code == 201, direct.text
    assert skill.status_code == 201, skill.text
    assert direct.json()["run"]["input_summary"] == skill.json()["run"]["input_summary"]
    assert direct.json()["run"]["prompt_version"] == "requirement-analysis.direct.v1"
    assert skill.json()["run"]["prompt_version"] == "requirement-analysis.skill.v1"
    assert skill.json()["run"]["skill_version"] == "ai-test-design-requirement-analysis.v1"
    assert "Step 00" not in service.prompts[0]
    assert "Step 00" in service.prompts[1] and "Step 08" in service.prompts[1]
    assert skill.json()["run"]["actual_usage"]["total_tokens"] == 200


def test_case_xlsx_respects_confirmed_template_field_mapping() -> None:
    content = _case_xlsx([{
        "id": "case-1", "title": "映射后的标题", "objective": "目标", "preconditions": ["前置"],
        "test_input": "输入", "steps": [{"order": 1, "action": "操作", "expected": "预期"}],
        "overall_expectation": "整体预期", "evidence_requirements": ["截图"], "priority": "P1",
        "module": "状态管理", "test_item": "状态切换",
    }], {"sheets": [{
        "name": "客户用例", "role": "case", "participates": True,
        "columns": [{"index": 1, "name": "客户标题"}, {"index": 2, "name": "业务模块"}],
        "field_mapping": {"客户标题": "title", "业务模块": "module"},
    }]})
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "客户标题" in xml and "映射后的标题" in xml
    assert "业务模块" in xml and "状态管理" in xml
