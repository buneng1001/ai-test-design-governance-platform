import base64
import io
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path

from fastapi.testclient import TestClient

from app.ai_service import ModelResponse
from app.main import create_app
from app.template_service import inspect_template
from app.v020_contracts import normalize_analysis_row
from app.v020_batching import aggregate_usage
from app.v020_export import _case_xlsx
from app.v020_run_service import estimate_input_tokens


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
    assert estimate["input_summary"]["source_fragment_count"] == 3
    assert estimate["input_summary"]["context_chunk_count"] == 1
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


def test_same_input_reuses_completed_analysis_without_adding_rows(client: TestClient) -> None:
    project_id = _project_and_material(client)
    first = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    })
    second = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    })

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["run"]["id"] == first.json()["run"]["id"]
    assert [item["id"] for item in second.json()["rows"]] == [item["id"] for item in first.json()["rows"]]
    workspace = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()
    assert len(workspace["runs"]) == 1
    assert "reused" not in workspace["runs"][0]
    assert len(workspace["analysis_rows"]) == len(first.json()["rows"])


def test_uploading_identical_material_keeps_requirement_version_and_existing_result(client: TestClient) -> None:
    project = client.post("/api/projects", json={
        "name": "相同资料项目", "test_object": "终端", "software_version": "v1",
        "description": "", "settings": {"requirement_language": "zh-CN"},
    }).json()
    payload = {
        "supplemental_notes": "关注异常", "files": [{
            "filename": "same.md", "media_type": "text/markdown",
            "content_base64": base64.b64encode("# 登录\n系统必须支持登录。".encode()).decode(),
        }],
    }
    first_upload = client.post(f"/api/v0.2/projects/{project['id']}/materials", json=payload)
    analysis = client.post(f"/api/v0.2/projects/{project['id']}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    })
    second_upload = client.post(f"/api/v0.2/projects/{project['id']}/materials", json=payload)
    workspace = client.get(f"/api/v0.2/projects/{project['id']}/workspace").json()

    assert first_upload.status_code == 201 and second_upload.status_code == 200
    assert second_upload.json()["requirement_version_reused"] is True
    assert second_upload.json()["requirement_version"]["id"] == first_upload.json()["requirement_version"]["id"]
    assert workspace["active_run_ids"]["analysis"] == analysis.json()["run"]["id"]

    changed_notes = client.post(f"/api/v0.2/projects/{project['id']}/materials", json={
        **payload, "supplemental_notes": "改为重点关注权限边界",
    })
    invalidated = client.get(f"/api/v0.2/projects/{project['id']}/workspace").json()
    assert changed_notes.status_code == 200
    assert changed_notes.json()["requirement_version_reused"] is True
    assert "analysis" not in invalidated["active_run_ids"]
    assert invalidated["analysis_rows"] == []


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
    active_rows = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()["analysis_rows"]
    assert [row["total_index"] for row in active_rows] == list(range(1, len(active_rows) + 1))

    reviewed = client.post(f"/api/v0.2/projects/{project_id}/review-runs", json={
        "mode": "local", "confirmed": True, "roles": ["product_manager", "test_manager"],
    })
    assert reviewed.status_code == 201
    assert {item["role"] for item in reviewed.json()["suggestions"]} == {"product_manager", "test_manager"}
    assert {item["role"] for item in reviewed.json()["run"]["role_reports"]} == {"product_manager", "test_manager"}
    review_item = reviewed.json()["suggestions"][0]
    accepted_review = client.patch(
        f"/api/v0.2/projects/{project_id}/review-suggestions/{review_item['id']}",
        json={"disposition": "accepted"},
    )
    assert accepted_review.status_code == 200
    assert accepted_review.json()["analysis_row"]["selected"] is False
    assert accepted_review.json()["analysis_row"]["origin"] == "review"
    review_export = client.get(f"/api/v0.2/projects/{project_id}/exports/review?format=json").json()
    assert {item["role"] for item in review_export["reports"]} == {"product_manager", "test_manager"}
    assert client.post(f"/api/v0.2/projects/{project_id}/review-skip").status_code == 200


def test_legacy_analysis_row_is_normalized_for_unified_table_and_case_generation() -> None:
    normalized = normalize_analysis_row({
        "id": "legacy-row", "test_item": "历史测试项", "source": "legacy.md · 第 1 行",
        "source_reference_id": "legacy-source", "selected": True,
    }, 7)

    assert normalized["total_index"] == 7
    assert normalized["test_basis"] == "历史结果未单列测试项依据"
    assert normalized["test_source"] == "legacy.md · 第 1 行"
    assert normalized["test_type"] == "功能测试"
    assert normalized["priority"] == "P2"
    assert normalized["related_requirement_id"] == "legacy-source"


def test_token_estimate_is_conservative_for_chinese_materials() -> None:
    assert estimate_input_tokens("中" * 1000) >= 1000
    assert estimate_input_tokens("a" * 1000) == 250


def test_partial_provider_usage_is_not_reported_as_complete_total() -> None:
    usage = aggregate_usage([
        {"status": "available", "input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        {"status": "unavailable", "reason": "供应商未返回"},
    ])
    assert usage["status"] == "unavailable"
    assert "不能可靠汇总" in usage["reason"]


def test_later_stages_reuse_same_input_instead_of_stacking(client: TestClient) -> None:
    project_id = _project_and_material(client)
    rows = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    }).json()["rows"]
    client.patch(f"/api/v0.2/projects/{project_id}/analysis-selection", json={
        "row_ids": [rows[0]["id"]], "selected": True,
    })

    endpoints = [
        ("suggestion-runs", {"mode": "local", "confirmed": True}),
        ("review-runs", {"mode": "local", "confirmed": True, "roles": ["test_manager"]}),
        ("case-runs", {"mode": "local", "confirmed": True, "template_mode": "default",
                       "supplemental_requirements": ""}),
    ]
    for endpoint, payload in endpoints:
        first = client.post(f"/api/v0.2/projects/{project_id}/{endpoint}", json=payload)
        second = client.post(f"/api/v0.2/projects/{project_id}/{endpoint}", json=payload)
        assert first.status_code == 201, first.text
        assert second.status_code == 200, second.text
        assert second.json()["reused"] is True
        assert second.json()["run"]["id"] == first.json()["run"]["id"]

    workspace = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()
    assert len([run for run in workspace["runs"] if run["page"] == "suggestions"]) == 1
    assert len([run for run in workspace["runs"] if run["page"] == "review"]) == 1
    assert len([run for run in workspace["runs"] if run["page"] == "cases"]) == 1
    assert len(workspace["suggestions"]) == 1
    assert len(workspace["review_suggestions"]) == 1
    assert len(workspace["case_generations"]) == 1


def test_reusing_older_case_input_switches_current_result_without_new_generation(client: TestClient) -> None:
    project_id = _project_and_material(client)
    rows = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    }).json()["rows"]
    client.patch(f"/api/v0.2/projects/{project_id}/analysis-selection", json={
        "row_ids": [rows[0]["id"]], "selected": True,
    })
    first = client.post(f"/api/v0.2/projects/{project_id}/case-runs", json={
        "mode": "local", "confirmed": True, "template_mode": "default",
        "supplemental_requirements": "只生成核心路径",
    })
    second = client.post(f"/api/v0.2/projects/{project_id}/case-runs", json={
        "mode": "local", "confirmed": True, "template_mode": "default",
        "supplemental_requirements": "补充异常路径",
    })
    reused = client.post(f"/api/v0.2/projects/{project_id}/case-runs", json={
        "mode": "local", "confirmed": True, "template_mode": "default",
        "supplemental_requirements": "只生成核心路径",
    })

    assert first.status_code == 201 and second.status_code == 201
    assert reused.status_code == 200 and reused.json()["reused"] is True
    workspace = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()
    assert workspace["active_run_ids"]["cases"] == first.json()["run"]["id"]
    assert len(workspace["case_generations"]) == 2
    exported = client.get(f"/api/v0.2/projects/{project_id}/exports/cases?format=json").json()
    assert exported["run_id"] == first.json()["run"]["id"]


def test_new_requirement_version_does_not_mix_old_accepted_suggestions(client: TestClient) -> None:
    project_id = _project_and_material(client)
    analysis = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    }).json()
    client.patch(f"/api/v0.2/projects/{project_id}/analysis-selection", json={
        "row_ids": [analysis["rows"][0]["id"]], "selected": True,
    })
    suggestion = client.post(f"/api/v0.2/projects/{project_id}/suggestion-runs", json={
        "mode": "local", "confirmed": True,
    }).json()["suggestions"][0]
    client.patch(f"/api/v0.2/projects/{project_id}/suggestions/{suggestion['id']}", json={
        "disposition": "accepted",
    })
    assert any(row["origin"] == "suggestion" for row in client.get(
        f"/api/v0.2/projects/{project_id}/workspace"
    ).json()["analysis_rows"])

    upload = client.post(f"/api/v0.2/projects/{project_id}/materials", json={
        "supplemental_notes": "改为关注升级流程。",
        "files": [{
            "filename": "upgrade.md", "media_type": "text/markdown",
            "content_base64": base64.b64encode("# 升级\n系统必须校验升级包签名。".encode()).decode(),
        }],
    })
    assert upload.status_code == 201
    new_analysis = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", json={
        "mode": "local", "confirmed": True,
    })
    assert new_analysis.status_code == 201
    restored = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()
    assert all(row["run_id"] == new_analysis.json()["run"]["id"] for row in restored["analysis_rows"])
    assert any(row["origin"] == "suggestion" for row in restored["analysis_history_rows"])
    assert restored["suggestions"] == []
    assert "suggestions" not in restored["active_run_ids"]


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
    assert [item["name"] for item in body["template"]["sheets"][0]["columns"]] == [
        "用例编号", "测试用例标题", "优先级", "预置条件", "输入", "操作步骤", "预期结果",
        "测试类型", "模块", "测试项", "附件", "软件版本",
    ]
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
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "人工编辑后的标题" not in sheet_xml
        assert "v0.2.0" in sheet_xml
        assert any(test_type in sheet_xml for test_type in ("功能测试", "异常测试"))
    assert len(client.get(f"/api/v0.2/projects/{project_id}/workspace").json()["exports"]) == 2
    exact_export = client.get(
        f"/api/v0.2/projects/{project_id}/exports/cases?format=json&run_id={body['run']['id']}"
    )
    assert exact_export.json()["run_id"] == body["run"]["id"]
    restored = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()
    assert restored["case_generations"][0]["scope_ids"] == selected_ids
    assert restored["exports"][-1]["record_id"] == body["run"]["id"]

    downloaded = client.get(f"/api/v0.2/projects/{project_id}/case-template/download")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    for header in body["template"]["sheets"][0]["field_mapping"]:
        assert header in sheet_xml
    format_name, parsed_sheets, diagnostics = inspect_template(
        "默认测试用例模板.xlsx", base64.b64encode(downloaded.content).decode("ascii"),
    )
    assert format_name == "xlsx"
    assert diagnostics == []
    assert [column.name for column in parsed_sheets[0].columns] == [
        item["name"] for item in body["template"]["sheets"][0]["columns"]
    ]


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
            "module": "状态管理", "test_item": "验证状态切换耗时",
            "test_basis": "约束包含明确时限", "source_reference_id": "input-1",
            "test_type": "性能测试", "priority": "P1", "related_requirement_id": "REQ-001",
        }]}, input_tokens=120, output_tokens=80, total_tokens=200)


class MaterialUnderstandingModelService:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        if "requirement-analysis.direct.v4" in request.prompt_override:
            return ModelResponse(raw_output={"rows": [{
                "module": "状态管理", "test_item": "验证状态切换耗时",
                "test_basis": "AI 整理结果包含明确时限", "source_reference_id": "input-1",
                "test_type": "性能测试", "priority": "P1", "related_requirement_id": "REQ-001",
            }]}, input_tokens=70, output_tokens=40, total_tokens=110)
        return ModelResponse(raw_output={
            "overview": "资料描述智能终端的状态切换时限与异常提示要求。",
            "organized_fragments": [{
                "source_reference_id": "input-1", "title": "状态管理",
                "summary": "设备状态切换必须在 2 秒内完成，异常时显示错误提示。",
                "key_points": ["状态切换时限为 2 秒", "异常状态必须显示错误提示"],
                "constraints": ["完成时间不超过 2 秒"], "ambiguities": [],
            }],
        }, input_tokens=90, output_tokens=60, total_tokens=150)


class TimeoutModelService:
    def complete(self, _request) -> ModelResponse:
        return ModelResponse(error_code="provider_timeout", retryable=True, diagnostic="TimeoutError")


class BatchedAnalysisModelService:
    def __init__(self, fail_first: bool = False) -> None:
        self.prompts: list[str] = []
        self.fail_first = fail_first

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        if self.fail_first:
            self.fail_first = False
            return ModelResponse(error_code="provider_timeout", retryable=True, diagnostic="TimeoutError")
        source_ids = sorted(set(re.findall(r'"source_reference_id":"(input-\d+)"', request.prompt_override)))
        return ModelResponse(raw_output={"rows": [{
            "module": "状态管理", "test_item": f"验证 {source_id} 对应功能",
            "test_basis": "来源中存在明确要求", "source_reference_id": source_id,
            "test_type": "功能测试", "priority": "P1", "related_requirement_id": source_id,
        } for source_id in source_ids]}, input_tokens=100, output_tokens=50, total_tokens=150)


class CancellableModelService:
    def __init__(self) -> None:
        self.started = Event()

    def complete(self, request) -> ModelResponse:
        self.started.set()
        for _ in range(500):
            if request.cancel_requested and request.cancel_requested():
                return ModelResponse(error_code="provider_cancelled", retryable=False)
            time.sleep(0.01)
        return ModelResponse(error_code="provider_timeout", retryable=True)


class ResumeModelService(BatchedAnalysisModelService):
    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def complete(self, request) -> ModelResponse:
        self.call_count += 1
        if self.call_count in {2, 3}:
            self.prompts.append(request.prompt_override)
            return ModelResponse(error_code="provider_timeout", retryable=True)
        return super().complete(request)


class InvalidSourceModelService:
    def complete(self, _request) -> ModelResponse:
        return ModelResponse(raw_output={"rows": [{
            "module": "越界", "test_item": "越界来源", "test_basis": "无效来源",
            "source_reference_id": "input-999", "test_type": "功能测试", "priority": "P1",
            "related_requirement_id": "REQ-X",
        }]})


def _project_with_many_sections(client: TestClient, count: int = 9) -> int:
    project = client.post("/api/projects", json={
        "name": "分批项目", "test_object": "智能终端", "software_version": "v0.2.0",
        "description": "", "settings": {"requirement_language": "zh-CN"},
    }).json()
    document = "\n".join(
        f"# 模块 {index}\n系统必须支持第 {index} 项功能，并处理对应异常。" for index in range(1, count + 1)
    )
    response = client.post(f"/api/v0.2/projects/{project['id']}/materials", json={
        "supplemental_notes": "", "files": [{
            "filename": "many.md", "media_type": "text/markdown",
            "content_base64": base64.b64encode(document.encode()).decode(),
        }],
    })
    assert response.status_code == 201
    return project["id"]


def test_preflight_applies_context_limit_to_each_bounded_request_not_full_document(tmp_path: Path, monkeypatch) -> None:
    application = create_app(
        tmp_path / "v020-large-preflight.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=BatchedAnalysisModelService(),
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project = client.post("/api/projects", json={
            "name": "长资料", "test_object": "终端", "software_version": "v1",
            "description": "", "settings": {"requirement_language": "zh-CN"},
        }).json()
        document = "\n".join(f"# 模块 {index}\n{'需求内容' * 250}" for index in range(40))
        client.post(f"/api/v0.2/projects/{project['id']}/materials", json={
            "supplemental_notes": "", "files": [{"filename": "large.md", "media_type": "text/markdown",
                "content_base64": base64.b64encode(document.encode()).decode()}],
        })
        headers = {"X-Session-ID": "large-preflight"}
        config = {"provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
                  "api_key": "test-only-secret", "remember_api_key": False}
        client.post("/api/ai-session-config/test", headers=headers, json=config)
        response = client.post(f"/api/v0.2/projects/{project['id']}/run-preflight", headers=headers, json={
            "page": "analysis", "mode": "direct",
        })

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["estimated_input_tokens"] > 32_000
    assert result["max_request_input_tokens"] + result["max_output_tokens"] < 32_000
    assert result["request_count"] == 20


def test_real_analysis_runs_in_bounded_batches_and_records_progress(tmp_path: Path, monkeypatch) -> None:
    service = BatchedAnalysisModelService()
    application = create_app(
        tmp_path / "v020-batches.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client)
        headers = {"X-Session-ID": "v020-batches"}
        config = {"provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
                  "api_key": "test-only-secret", "remember_api_key": False}
        assert client.post("/api/ai-session-config/test", headers=headers, json=config).json()["success"] is True
        preflight = client.post(f"/api/v0.2/projects/{project_id}/run-preflight", headers=headers, json={
            "page": "analysis", "mode": "direct",
        }).json()
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })

    assert response.status_code == 201, response.text
    assert preflight["request_count"] == 5
    assert len(service.prompts) == 5
    assert all("requirement-analysis.direct.v4" in prompt for prompt in service.prompts)
    run = response.json()["run"]
    assert run["progress"] == {"completed_units": 5, "total_units": 5, "stage": "保存结果"}
    assert len(run["checkpoints"]) == 5
    assert run["actual_usage"]["total_tokens"] == 750
    assert len(response.json()["rows"]) == 9


def test_retryable_batch_failure_is_retried_once(tmp_path: Path, monkeypatch) -> None:
    service = BatchedAnalysisModelService(fail_first=True)
    application = create_app(
        tmp_path / "v020-batch-retry.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client, count=1)
        headers = {"X-Session-ID": "v020-batch-retry"}
        config = {"provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
                  "api_key": "test-only-secret", "remember_api_key": False}
        client.post("/api/ai-session-config/test", headers=headers, json=config)
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })

    assert response.status_code == 201, response.text
    assert len(service.prompts) == 2
    assert len(response.json()["run"]["attempts"]) == 2


def test_running_request_can_be_cancelled_with_known_run_id(tmp_path: Path, monkeypatch) -> None:
    service = CancellableModelService()
    application = create_app(
        tmp_path / "v020-cancel.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client, count=1)
        headers = {"X-Session-ID": "v020-cancel"}
        config = {"provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
                  "api_key": "test-only-secret", "remember_api_key": False}
        client.post("/api/ai-session-config/test", headers=headers, json=config)
        run_id = "run-cancel-known-12345678"
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.post, f"/api/v0.2/projects/{project_id}/analysis-runs",
                                      headers=headers, json={"mode": "direct", "confirmed": True, "run_id": run_id})
            assert service.started.wait(timeout=2)
            progress = client.get(f"/api/v0.2/projects/{project_id}/runs/{run_id}")
            stopped = client.post(f"/api/v0.2/projects/{project_id}/runs/{run_id}/cancel")
            response = pending.result(timeout=3)
        final_run = client.get(f"/api/v0.2/projects/{project_id}/runs/{run_id}").json()

    assert progress.status_code == 200 and progress.json()["status"] == "running"
    assert stopped.status_code == 200 and stopped.json()["cancel_requested"] is True
    assert response.status_code == 409
    assert final_run["status"] == "stopped"
    assert final_run["progress"]["completed_units"] == 0


def test_failed_batched_run_resumes_from_last_valid_checkpoint(tmp_path: Path, monkeypatch) -> None:
    service = ResumeModelService()
    application = create_app(
        tmp_path / "v020-resume.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client)
        headers = {"X-Session-ID": "v020-resume"}
        config = {"provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
                  "api_key": "test-only-secret", "remember_api_key": False}
        client.post("/api/ai-session-config/test", headers=headers, json=config)
        first = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })
        second = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })

    assert first.status_code == 504
    assert second.status_code == 201, second.text
    assert second.json()["run"]["resumed_from_run_id"]
    assert second.json()["run"]["progress"]["completed_units"] == 5
    assert service.call_count == 7


def test_invalid_batch_is_rejected_before_checkpoint_is_saved(tmp_path: Path, monkeypatch) -> None:
    application = create_app(
        tmp_path / "v020-invalid-checkpoint.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=InvalidSourceModelService(),
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client, count=1)
        headers = {"X-Session-ID": "v020-invalid-checkpoint"}
        config = {"provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
                  "api_key": "test-only-secret", "remember_api_key": False}
        client.post("/api/ai-session-config/test", headers=headers, json=config)
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })
        workspace = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()

    assert response.status_code == 422
    failed = workspace["runs"][-1]
    assert failed["status"] == "failed"
    assert failed["checkpoints"] == []


def test_material_understanding_is_persisted_and_reused_for_unchanged_input(tmp_path: Path, monkeypatch) -> None:
    service = MaterialUnderstandingModelService()
    application = create_app(
        tmp_path / "v020-understanding.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_and_material(client)
        headers = {"X-Session-ID": "v020-understanding-client"}
        config = {
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        }
        assert client.post("/api/ai-session-config/test", headers=headers, json=config).json()["success"] is True
        first = client.post(f"/api/v0.2/projects/{project_id}/material-understanding-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })
        second = client.post(f"/api/v0.2/projects/{project_id}/material-understanding-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })
        workspace = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()
        replacement = client.post(f"/api/v0.2/projects/{project_id}/materials", json={
            "supplemental_notes": "改为关注升级流程。",
            "files": [{
                "filename": "upgrade.md", "media_type": "text/markdown",
                "content_base64": base64.b64encode("# 升级\n系统必须校验升级包签名。".encode()).decode(),
            }],
        })
        invalidated = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()

    assert first.status_code == 201, first.text
    assert first.json()["understanding"]["overview"].startswith("资料描述")
    assert first.json()["understanding"]["organized_fragments"][0]["source_reference_id"] == "input-1"
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["run"]["id"] == first.json()["run"]["id"]
    assert workspace["material_understanding"]["run_id"] == first.json()["run"]["id"]
    assert replacement.status_code == 201
    assert invalidated["material_understanding"] is None
    assert "understanding" not in invalidated["active_run_ids"]
    assert len(service.prompts) == 1
    assert '"source_reference_id":"input-1"' in service.prompts[0]


def test_analysis_uses_persisted_material_understanding_as_model_context(tmp_path: Path, monkeypatch) -> None:
    service = MaterialUnderstandingModelService()
    application = create_app(
        tmp_path / "v020-understanding-analysis.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_and_material(client)
        headers = {"X-Session-ID": "v020-understanding-analysis"}
        config = {
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        }
        assert client.post("/api/ai-session-config/test", headers=headers, json=config).json()["success"] is True
        understood = client.post(
            f"/api/v0.2/projects/{project_id}/material-understanding-runs", headers=headers,
            json={"mode": "direct", "confirmed": True},
        )
        analysis = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })

    assert understood.status_code == 201
    assert analysis.status_code == 201, analysis.text
    assert analysis.json()["run"]["input_summary"]["material_understanding_used"] is True
    assert analysis.json()["rows"][0]["test_basis"] == "AI 整理结果包含明确时限"
    assert len(service.prompts) == 2
    assert '"material_understanding_used":true' in service.prompts[1]
    assert "状态切换时限为 2 秒" in service.prompts[1]


def test_model_timeout_returns_actionable_error_and_persists_failed_run(tmp_path: Path, monkeypatch) -> None:
    application = create_app(
        tmp_path / "v020-timeout.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=TimeoutModelService(),
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_and_material(client)
        headers = {"X-Session-ID": "v020-timeout"}
        config = {
            "provider": "siliconflow", "model": "Qwen3.5-27B",
            "base_url": "https://api.siliconflow.cn/v1", "api_key": "test-only-secret",
            "remember_api_key": False,
        }
        assert client.post("/api/ai-session-config/test", headers=headers, json=config).json()["success"] is True
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })
        workspace = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["stage"] == "model_call"
    assert detail["error_type"] == "timeout"
    assert detail["retryable"] is True
    assert "180 秒" in detail["user_message"]
    failed = workspace["runs"][-1]
    assert failed["status"] == "failed"
    assert failed["duration_ms"] is not None
    assert "180 秒" in failed["error"]


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
    assert direct.json()["run"]["prompt_version"] == "requirement-analysis.direct.v4"
    assert skill.json()["run"]["prompt_version"] == "requirement-analysis.skill.v4"
    assert skill.json()["run"]["skill_version"] == "ai-test-design-requirement-analysis.v1"
    assert "Step 00" not in service.prompts[0]
    assert "Step 00" in service.prompts[1] and "Step 08" in service.prompts[1]
    assert skill.json()["run"]["actual_usage"]["total_tokens"] == 200


def test_real_model_is_not_called_twice_for_identical_completed_input(tmp_path: Path, monkeypatch) -> None:
    service = CaptureModelService()
    application = create_app(
        tmp_path / "v020-ai-reuse.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_and_material(client)
        headers = {"X-Session-ID": "v020-ai-reuse"}
        config = {
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        }
        assert client.post("/api/ai-session-config/test", headers=headers, json=config).json()["success"] is True
        first = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })
        second = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "direct", "confirmed": True,
        })

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert len(service.prompts) == 1


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
