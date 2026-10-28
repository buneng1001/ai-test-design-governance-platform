import base64
import io
import json
import re
import sqlite3
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
from app.v020_run_repository import V020RunRepository
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
        return _analysis_stage_response(request.prompt_override)


class MaterialUnderstandingModelService:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        if "requirement-analysis.skill.v7" in request.prompt_override:
            return _analysis_stage_response(request.prompt_override, basis="AI 整理结果包含明确时限")
        source_ids = sorted(set(re.findall(r'"source_reference_id":"(input-\d+)"', request.prompt_override)))
        return ModelResponse(raw_output={
            "overview": "资料描述智能终端的状态切换时限与异常提示要求。",
            "organized_fragments": [{
                "source_reference_id": source_id, "title": f"状态管理 {source_id}",
                "summary": "设备状态切换必须在 2 秒内完成，异常时显示错误提示。",
                "key_points": ["状态切换时限为 2 秒", "异常状态必须显示错误提示"],
                "constraints": ["完成时间不超过 2 秒"], "ambiguities": [],
            } for source_id in source_ids],
        }, input_tokens=90, output_tokens=60, total_tokens=150)


class TimeoutModelService:
    def complete(self, _request) -> ModelResponse:
        return ModelResponse(error_code="provider_timeout", retryable=True, diagnostic="TimeoutError")


class TruncatedModelService:
    def complete(self, _request) -> ModelResponse:
        return ModelResponse(
            error_code="provider_response_truncated", retryable=False, diagnostic="finish_reason=length",
            finish_reason="length", response_length=8192, duration_ms=2345, first_event_ms=120,
        )


class AdaptiveBatchModelService:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.max_tokens: list[int] = []
        self.truncated_stages: set[str] = set()

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        self.max_tokens.append(request.model_parameters.max_tokens)
        payload = json.loads(request.prompt_override.rsplit("\n", 1)[-1])
        stage = re.search(r"当前阶段：(S\d{2})", request.prompt_override).group(1)
        batch_scope = payload.get("batch_scope", {})
        scope_ids = batch_scope.get("requirement_ids") or batch_scope.get("source_reference_ids", [])
        if len(scope_ids) > 1 and stage not in self.truncated_stages:
            self.truncated_stages.add(stage)
            return ModelResponse(
                error_code="provider_response_truncated", retryable=False, diagnostic="finish_reason=length",
                finish_reason="length", response_length=8192, duration_ms=100, first_event_ms=10,
            )
        return _analysis_stage_response(request.prompt_override)


class MidStageBatchFailureModelService:
    def __init__(self) -> None:
        self.scopes: list[tuple[str, tuple[str, ...]]] = []
        self.failed = False

    def complete(self, request) -> ModelResponse:
        payload = json.loads(request.prompt_override.rsplit("\n", 1)[-1])
        stage = re.search(r"当前阶段：(S\d{2})", request.prompt_override).group(1)
        scope = tuple(
            payload.get("batch_scope", {}).get("requirement_ids")
            or payload.get("batch_scope", {}).get("source_reference_ids", [])
        )
        self.scopes.append((stage, scope))
        if stage == "S03" and payload["batch_scope"]["batch_number"] == 2 and not self.failed:
            self.failed = True
            return ModelResponse(error_code="provider_http_400", retryable=False, diagnostic="simulated")
        return _analysis_stage_response(request.prompt_override)


class AnalysisModelService:
    def __init__(self, fail_first: bool = False) -> None:
        self.prompts: list[str] = []
        self.fail_first = fail_first

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        if self.fail_first:
            self.fail_first = False
            return ModelResponse(error_code="provider_timeout", retryable=True, diagnostic="TimeoutError")
        return _analysis_stage_response(request.prompt_override)


class StageFailureModelService:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.failed = False

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        if "当前阶段：S03" in request.prompt_override and not self.failed:
            self.failed = True
            return ModelResponse(error_code="provider_http_400", retryable=False, diagnostic="simulated")
        return _analysis_stage_response(request.prompt_override)


class RecoverableIncompleteS04ModelService:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        if request.prompt_version.endswith(".repair"):
            return _analysis_stage_response(request.prompt_override)
        response = _analysis_stage_response(request.prompt_override)
        if "当前阶段：S04" not in request.prompt_override:
            return response
        raw = response.raw_output
        assert isinstance(raw, dict)
        for row in raw["rows"]:
            row.pop("test_type")
            row.pop("priority")
        return response


class IrrecoverableS00StructureModelService:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        response = _analysis_stage_response(request.prompt_override)
        if "当前阶段：S00" in request.prompt_override:
            raw = response.raw_output
            assert isinstance(raw, dict)
            raw.pop("source_coverage")
            raw["atomic_requirements"] = raw["atomic_requirements"][:-1]
            if raw["atomic_requirements"]:
                raw["atomic_requirements"][0].pop("statement")
        return response


class EchoedS00RepairContextModelService:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request) -> ModelResponse:
        self.prompts.append(request.prompt_override)
        if request.prompt_version.endswith(".repair"):
            return ModelResponse(raw_output=json.loads(request.prompt_override.rsplit("\n", 1)[-1]))
        response = _analysis_stage_response(request.prompt_override)
        if "当前阶段：S00" in request.prompt_override:
            raw = response.raw_output
            assert isinstance(raw, dict)
            raw.pop("source_coverage")
            raw["atomic_requirements"] = raw["atomic_requirements"][:-1]
        return response


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


class InvalidSourceModelService:
    def complete(self, request) -> ModelResponse:
        return _analysis_stage_response(request.prompt_override, invalid_source=True)


def _analysis_stage_response(prompt: str, *, basis: str = "来源中存在明确要求",
                             invalid_source: bool = False) -> ModelResponse:
    stage = re.search(r"当前阶段：(S\d{2})", prompt).group(1)
    payload = json.loads(prompt.rsplit("\n", 1)[-1])
    materials = payload.get("materials") or payload.get("materials_missing_coverage") or []
    source_ids = [item["source_reference_id"] for item in materials]
    source_ids = source_ids or payload.get("allowed_source_reference_ids") or ["input-1"]
    if invalid_source:
        source_ids = ["input-999"]
    prior_requirements = (
        payload.get("prior_stage_outputs", {}).get("S00", {}).get("atomic_requirements", [])
    )
    requirement_ids = (
        payload.get("batch_scope", {}).get("requirement_ids")
        or payload.get("allowed_requirement_ids")
        or [item["requirement_id"] for item in prior_requirements]
        or [f"REQ-{index:03d}" for index in range(1, len(source_ids) + 1)]
    )
    source_by_requirement = {
        item["requirement_id"]: item["source_reference_id"] for item in prior_requirements
    }
    if stage == "S00":
        raw = {"atomic_requirements": [{
            "requirement_id": requirement_id, "statement": f"{source_id} 的明确需求",
            "source_reference_id": source_id,
        } for source_id, requirement_id in zip(source_ids, requirement_ids)],
            "source_coverage": [{
                "source_reference_id": source_id, "requirement_ids": [requirement_id],
                "no_requirement_reason": "",
            } for source_id, requirement_id in zip(source_ids, requirement_ids)],
            "questions": []}
    elif stage == "S01":
        raw = {"functions": [{
            "function_id": f"FUN-{index:03d}", "module": "状态管理", "name": f"功能 {index}",
            "description": "执行资料中描述的功能", "requirement_ids": [requirement_id],
        } for index, requirement_id in enumerate(requirement_ids, start=1)]}
    elif stage == "S02":
        raw = {"rules": [{"rule_id": f"RULE-{index:03d}", "description": "遵守资料约束",
                           "requirement_ids": [requirement_id]}
                          for index, requirement_id in enumerate(requirement_ids, start=1)]}
    else:
        stage_type = {"S03": "功能测试", "S04": "异常测试", "S05": "边界测试", "S06": "安全性测试"}[stage]
        pairs = [
            (source_by_requirement.get(requirement_id, source_ids[min(index, len(source_ids) - 1)]), requirement_id)
            for index, requirement_id in enumerate(requirement_ids)
        ]
        if stage != "S03":
            pairs = pairs[:1]
        raw = {"rows": [{
            "module": "状态管理", "test_item": f"{stage} 验证 {source_id} 对应功能",
            "test_basis": basis, "source_reference_id": source_id, "test_type": stage_type,
            "priority": "P1", "related_requirement_id": requirement_id,
        } for source_id, requirement_id in pairs]}
    return ModelResponse(raw_output=raw, input_tokens=100, output_tokens=50, total_tokens=150,
                         finish_reason="stop", response_length=512)


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


def test_preflight_accepts_a_large_document_when_each_semantic_batch_fits_the_context_limit(
    tmp_path: Path, monkeypatch,
) -> None:
    application = create_app(
        tmp_path / "v020-large-preflight.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=AnalysisModelService(),
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
            "page": "analysis", "mode": "skill",
        })

    assert response.status_code == 200, response.text
    assert response.json()["request_count"] > 7
    assert response.json()["max_request_input_tokens"] + response.json()["max_output_tokens"] <= 32_000


def test_skill_analysis_runs_stages_against_the_complete_parsed_document(tmp_path: Path, monkeypatch) -> None:
    service = AnalysisModelService()
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
            "page": "analysis", "mode": "skill",
        }).json()
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert response.status_code == 201, response.text
    assert preflight["request_count"] == 15
    assert preflight["workflow_stage_count"] == 9
    assert preflight["max_output_tokens"] == 8_192
    assert preflight["max_request_count"] == 120
    assert preflight["max_total_output_tokens"] == 983_040
    assert preflight["retry_policy"] == {"max_retries_per_batch": 1, "max_additional_requests": 105}
    assert preflight["repair_policy"] == {"max_requests_per_batch": 1, "max_additional_requests": 105}
    assert preflight["timeout_policy"]["request_total_seconds"] == 600
    assert len(service.prompts) == 15
    stage_prompts = {
        stage: [prompt for prompt in service.prompts if f"当前阶段：{stage}" in prompt]
        for stage in ("S00", "S01", "S02", "S03", "S04", "S05", "S06")
    }
    assert [len(stage_prompts[stage]) for stage in stage_prompts] == [3, 2, 2, 2, 2, 2, 2]
    assert all("requirement-analysis.skill.v7" in prompt for prompt in service.prompts)
    assert all("七个字段" not in prompt for stage in ("S00", "S01", "S02") for prompt in stage_prompts[stage])
    assert all("七个字段" in prompt for stage in ("S03", "S04", "S05", "S06")
               for prompt in stage_prompts[stage])
    s00_scopes = [
        json.loads(prompt.rsplit("\n", 1)[-1])["batch_scope"]["source_reference_ids"]
        for prompt in stage_prompts["S00"]
    ]
    assert sum("input-1" in scope for scope in s00_scopes) == 1
    assert sum("input-9" in scope for scope in s00_scopes) == 1
    run = response.json()["run"]
    assert run["max_request_count"] == 120
    assert run["retry_policy"]["max_retries_per_batch"] == 1
    assert run["repair_policy"]["max_requests_per_batch"] == 1
    assert run["progress"] == {"completed_units": 9, "total_units": 9, "stage": "保存结果"}
    assert [item["stage_id"] for item in run["checkpoints"] if item.get("checkpoint_type") != "skill_batch"] == [
        "S00", "S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08",
    ]
    assert run["actual_usage"]["total_tokens"] == 2_250
    assert len(response.json()["rows"]) >= 9


def test_skill_preflight_rejects_a_regular_plan_above_the_hard_request_limit(
    client: TestClient, monkeypatch,
) -> None:
    project_id = _project_and_material(client)
    monkeypatch.setattr("app.v020_run_service.skill_preflight_prompts", lambda _context: ["prompt"] * 121)

    response = client.post(f"/api/v0.2/projects/{project_id}/run-preflight", json={
        "page": "analysis", "mode": "skill",
    })

    assert response.status_code == 422
    assert "预计需要 121 次常规模型调用" in response.json()["detail"]
    assert "120 次硬上限" in response.json()["detail"]


def test_skill_analysis_batches_every_model_stage_and_shrinks_a_truncated_batch(
    tmp_path: Path, monkeypatch,
) -> None:
    service = AdaptiveBatchModelService()
    application = create_app(
        tmp_path / "v020-adaptive-stage-batches.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client, count=9)
        headers = {"X-Session-ID": "v020-adaptive-stage-batches"}
        client.post("/api/ai-session-config/test", headers=headers, json={
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        })
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert response.status_code == 201, response.text
    run = response.json()["run"]
    model_stages = {f"S{index:02d}" for index in range(7)}
    batch_checkpoints = [
        checkpoint for checkpoint in run["checkpoints"]
        if checkpoint.get("checkpoint_type") == "skill_batch"
    ]
    assert {checkpoint["stage_id"] for checkpoint in batch_checkpoints} == model_stages
    assert all(service.max_tokens[index] == 8192 for index in range(len(service.max_tokens)))
    assert {
        attempt["stage_id"] for attempt in run["attempts"]
        if attempt.get("error_code") == "provider_response_truncated"
    } == model_stages
    assert run["status"] == "completed"
    assert len(run["attempts"]) <= run["max_request_count"]
    assert run["progress"]["completed_units"] == 9


def test_skill_analysis_resumes_from_the_last_completed_stage_batch(tmp_path: Path, monkeypatch) -> None:
    service = MidStageBatchFailureModelService()
    application = create_app(
        tmp_path / "v020-stage-batch-resume.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client, count=9)
        headers = {"X-Session-ID": "v020-stage-batch-resume"}
        client.post("/api/ai-session-config/test", headers=headers, json={
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        })
        first = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })
        failed_run = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()["runs"][-1]
        second = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert first.status_code == 502
    completed_s03 = [
        checkpoint for checkpoint in failed_run["checkpoints"]
        if checkpoint.get("checkpoint_type") == "skill_batch" and checkpoint.get("stage_id") == "S03"
    ]
    assert len(completed_s03) == 1
    first_scope = tuple(completed_s03[0]["scope_ids"])
    assert second.status_code == 201, second.text
    assert second.json()["run"]["resumed_from_run_id"] == failed_run["id"]
    assert sum(stage == "S03" and scope == first_scope for stage, scope in service.scopes) == 1


def test_material_understanding_sends_the_complete_parsed_document_in_one_request(
    tmp_path: Path, monkeypatch,
) -> None:
    service = MaterialUnderstandingModelService()
    application = create_app(
        tmp_path / "v020-understanding-single-request.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client)
        headers = {"X-Session-ID": "v020-understanding-single-request"}
        config = {
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        }
        assert client.post("/api/ai-session-config/test", headers=headers, json=config).json()["success"] is True
        preflight = client.post(f"/api/v0.2/projects/{project_id}/run-preflight", headers=headers, json={
            "page": "understanding", "mode": "direct",
        })
        response = client.post(
            f"/api/v0.2/projects/{project_id}/material-understanding-runs", headers=headers,
            json={"mode": "direct", "confirmed": True},
        )

    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["request_count"] == 1
    assert response.status_code == 201, response.text
    assert len(service.prompts) == 1
    assert '"source_reference_id":"input-1"' in service.prompts[0]
    assert '"source_reference_id":"input-9"' in service.prompts[0]
    assert len(response.json()["understanding"]["organized_fragments"]) == 9


def test_retryable_model_failure_is_retried_once(tmp_path: Path, monkeypatch) -> None:
    service = AnalysisModelService(fail_first=True)
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
            "mode": "skill", "confirmed": True,
        })

    assert response.status_code == 201, response.text
    assert len(service.prompts) == 8
    assert len(response.json()["run"]["attempts"]) == 8


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
                                      headers=headers, json={"mode": "skill", "confirmed": True, "run_id": run_id})
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


def test_failed_final_save_reuses_the_completed_model_request_checkpoint(tmp_path: Path, monkeypatch) -> None:
    service = AnalysisModelService()
    application = create_app(
        tmp_path / "v020-resume.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    original_set_active_run = V020RunRepository.set_active_run
    failed_once = False

    def fail_first_analysis_activation(self, project_id, page, run_id):
        nonlocal failed_once
        if page == "analysis" and not failed_once:
            failed_once = True
            raise sqlite3.IntegrityError("simulated legacy active-result constraint")
        return original_set_active_run(self, project_id, page, run_id)

    monkeypatch.setattr(V020RunRepository, "set_active_run", fail_first_analysis_activation)
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client)
        headers = {"X-Session-ID": "v020-resume"}
        config = {"provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
                  "api_key": "test-only-secret", "remember_api_key": False}
        client.post("/api/ai-session-config/test", headers=headers, json=config)
        first = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })
        prompt_count_after_first = len(service.prompts)
        second = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert first.status_code == 500
    assert second.status_code == 201, second.text
    assert second.json()["run"]["resumed_from_run_id"]
    assert second.json()["run"]["progress"]["completed_units"] == 9
    assert len(service.prompts) == prompt_count_after_first


def test_failed_skill_stage_resumes_without_repeating_completed_stages(tmp_path: Path, monkeypatch) -> None:
    service = StageFailureModelService()
    application = create_app(
        tmp_path / "v020-stage-resume.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client, count=1)
        headers = {"X-Session-ID": "v020-stage-resume"}
        client.post("/api/ai-session-config/test", headers=headers, json={
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        })
        first = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })
        failed_run = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()["runs"][-1]
        second = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert first.status_code == 502
    assert [
        item["stage_id"] for item in failed_run["checkpoints"]
        if item.get("checkpoint_type") != "skill_batch"
    ] == ["S00", "S01", "S02"]
    assert second.status_code == 201, second.text
    assert second.json()["run"]["resumed_from_run_id"]
    assert [re.search(r"当前阶段：(S\d{2})", prompt).group(1) for prompt in service.prompts] == [
        "S00", "S01", "S02", "S03", "S03", "S04", "S05", "S06",
    ]


def test_skill_repairs_missing_s04_fields_once_and_continues(tmp_path: Path, monkeypatch) -> None:
    service = RecoverableIncompleteS04ModelService()
    application = create_app(
        tmp_path / "v020-stage-repair.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client, count=1)
        headers = {"X-Session-ID": "v020-stage-repair"}
        client.post("/api/ai-session-config/test", headers=headers, json={
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        })
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert response.status_code == 201, response.text
    run = response.json()["run"]
    repaired = next(item for item in run["checkpoints"] if item["stage_id"] == "S04")
    assert repaired["repair_applied"] is True
    assert repaired["output"]["rows"][0]["test_type"] == "异常测试"
    assert repaired["output"]["rows"][0]["priority"] == "P1"
    assert sum("结构修复" in prompt for prompt in service.prompts) == 1


def test_skill_rejects_s00_when_business_content_is_still_invalid_after_repair(tmp_path: Path, monkeypatch) -> None:
    service = IrrecoverableS00StructureModelService()
    application = create_app(
        tmp_path / "v020-s00-coverage.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client, count=2)
        headers = {"X-Session-ID": "v020-s00-coverage"}
        client.post("/api/ai-session-config/test", headers=headers, json={
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        })
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert response.status_code == 422
    assert "S00" in response.json()["detail"]
    assert "statement" in response.json()["detail"]
    assert "errors.pydantic.dev" not in response.json()["detail"]
    assert sum("结构修复" in prompt for prompt in service.prompts) == 1


def test_skill_locally_rebuilds_missing_s00_coverage_instead_of_accepting_repair_context_echo(
    tmp_path: Path, monkeypatch,
) -> None:
    service = EchoedS00RepairContextModelService()
    application = create_app(
        tmp_path / "v020-s00-local-coverage-repair.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=service,
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_with_many_sections(client, count=2)
        headers = {"X-Session-ID": "v020-s00-local-coverage-repair"}
        client.post("/api/ai-session-config/test", headers=headers, json={
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        })
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert response.status_code == 201, response.text
    s00_batches = [
        item for item in response.json()["run"]["checkpoints"]
        if item.get("checkpoint_type") == "skill_batch" and item.get("stage_id") == "S00"
    ]
    assert s00_batches
    assert all(item["repair_applied"] is False for item in s00_batches)
    assert all(item["local_repair_applied"] is True for item in s00_batches)
    assert all(item["output"]["source_coverage"] for item in s00_batches)
    assert any(
        coverage["no_requirement_reason"]
        for item in s00_batches for coverage in item["output"]["source_coverage"]
    )
    assert not any("结构修复" in prompt for prompt in service.prompts)


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
            "mode": "skill", "confirmed": True,
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
            "mode": "skill", "confirmed": True,
        })

    assert understood.status_code == 201
    assert analysis.status_code == 201, analysis.text
    assert analysis.json()["run"]["input_summary"]["material_understanding_used"] is True
    assert analysis.json()["rows"][0]["test_basis"] == "AI 整理结果包含明确时限"
    assert len(service.prompts) == 8
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
            "mode": "skill", "confirmed": True,
        })
        workspace = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["stage"] == "model_call"
    assert detail["error_type"] == "timeout"
    assert detail["retryable"] is True
    assert "600 秒" in detail["user_message"]
    failed = workspace["runs"][-1]
    assert failed["status"] == "failed"
    assert failed["duration_ms"] is not None
    assert "600 秒" in failed["error"]


def test_truncated_model_output_reports_length_limit_and_persists_diagnostics(tmp_path: Path, monkeypatch) -> None:
    application = create_app(
        tmp_path / "v020-truncated.db", local_credentials_path=tmp_path / ".env.local",
        real_model_service=TruncatedModelService(),
    )

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    with TestClient(application) as client:
        project_id = _project_and_material(client)
        headers = {"X-Session-ID": "v020-truncated"}
        client.post("/api/ai-session-config/test", headers=headers, json={
            "provider": "custom", "model": "capture-model", "base_url": "https://example.invalid/v1",
            "api_key": "test-only-secret", "remember_api_key": False,
        })
        response = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })
        failed = client.get(f"/api/v0.2/projects/{project_id}/workspace").json()["runs"][-1]

    assert response.status_code == 502
    assert response.json()["detail"]["error_type"] == "output_truncated"
    assert "模型输出达到长度上限" in response.json()["detail"]["user_message"]
    assert failed["attempts"][-1] == {
        "unit": 1, "stage_id": "S00", "batch_scope_ids": ["input-1"], "attempt": 1,
        "operation": "generate", "error_code": "provider_response_truncated",
        "duration_ms": 2345, "first_event_ms": 120, "finish_reason": "length",
        "response_length": 8192, "diagnostic": "finish_reason=length",
    }


def test_direct_mode_is_disabled_and_skill_mode_runs_versioned_stages(tmp_path: Path, monkeypatch) -> None:
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

    assert direct.status_code == 422, direct.text
    assert "已停用" in direct.json()["detail"]
    assert skill.status_code == 201, skill.text
    assert skill.json()["run"]["prompt_version"] == "requirement-analysis.skill.v7"
    assert skill.json()["run"]["skill_version"] == "ai-test-design-requirement-analysis.v1"
    assert len(service.prompts) == 7
    assert "当前阶段：S00" in service.prompts[0]
    assert "当前阶段：S06" in service.prompts[-1]
    assert skill.json()["run"]["actual_usage"]["total_tokens"] == 1_050


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
            "mode": "skill", "confirmed": True,
        })
        second = client.post(f"/api/v0.2/projects/{project_id}/analysis-runs", headers=headers, json={
            "mode": "skill", "confirmed": True,
        })

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert len(service.prompts) == 7


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
