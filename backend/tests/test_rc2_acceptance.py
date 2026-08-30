import base64
import csv
import io
import os

import pytest
from fastapi.testclient import TestClient


def _encode_content_base64(content: str) -> str:
    return base64.b64encode(content.encode("utf-8")).decode("ascii")


def _create_project(client: TestClient) -> dict:
    response = client.post("/api/projects", json={
        "name": "rc.2 验收项目", "test_object": "虚构智能采集设备", "software_version": "v2.0.0",
        "description": "原创合成验收资料",
    })
    assert response.status_code == 201
    return response.json()


def _register_requirement(client: TestClient, project_id: int, filename: str, content: str) -> dict:
    response = client.post(f"/api/projects/{project_id}/assets", json={
        "name": filename, "asset_type": "requirement_material", "provenance_kind": "original_synthetic",
        "source": "测试工程师从零创作", "usage_permission": "project_owned", "model_permission": "allowed",
        "requirement_version": "V1", "purpose": "rc.2 验收", "content_base64": _encode_content_base64(content),
        "change_reason": "首次登记",
    })
    assert response.status_code == 201
    return {"asset_id": response.json()["id"], "filename": filename, "media_type": "text/markdown",
            "content_base64": _encode_content_base64(content)}


def _prepare_version(client: TestClient, project_id: int) -> dict:
    files = [
        _register_requirement(client, project_id, "SRS.md", "设备必须保存全部状态。"),
        _register_requirement(client, project_id, "implementation-spec.md", "设备只保存最近状态。"),
    ]
    package = client.post(f"/api/projects/{project_id}/requirement-packages", json={"files": files})
    assert package.status_code == 201
    package_id = package.json()["id"]
    version = client.post(
        f"/api/projects/{project_id}/requirement-packages/{package_id}/publish"
    )
    assert version.status_code == 201
    return version.json()


def _confirm_requirements(client: TestClient, project_id: int, analysis: dict) -> dict:
    for candidate in analysis["atomic_requirements"]:
        response = client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}"
            f"/atomic-requirements/{candidate['candidate_id']}",
            json={"decision": "accepted"},
        )
        assert response.status_code == 200
    for finding in analysis["findings"]:
        response = client.patch(
            f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/findings/{finding['finding_id']}",
            json={"status": "resolved"},
        )
        assert response.status_code == 200
    confirmed = client.post(
        f"/api/projects/{project_id}/requirement-reviews/{analysis['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    assert confirmed.status_code == 200
    return confirmed.json()


def _confirm_template(client: TestClient, project_id: int) -> int:
    content = "用例编号,测试用例标题,优先级,预置条件,输入,操作步骤,预期结果,测试类型,模块,测试项,"
    content += "测试结果,测试记录,测试前备注信息,计划执行时间,附件,软件版本,父记录\n"
    uploaded = client.post(f"/api/projects/{project_id}/template-mappings", json={
        "filename": "默认用例模板.csv", "content_base64": _encode_content_base64(content),
    })
    assert uploaded.status_code == 201
    mapping = uploaded.json()
    confirmed = client.post(f"/api/projects/{project_id}/template-mappings/{mapping['id']}/confirm", json={
        "confirmer_name": "测试工程师", "mappings": [{
            "sheet_name": "CSV", "role": "case", "participates": True, "title_row": 1,
            "field_mapping": {
                "用例编号": "external_case_number", "测试用例标题": "title", "优先级": "priority",
                "预置条件": "preconditions", "输入": "input", "操作步骤": "steps",
                "预期结果": "overall_expectation", "测试类型": "test_type", "模块": "module",
                "测试项": "test_item", "测试结果": "test_result", "测试记录": "test_record",
                "测试前备注信息": "pre_test_notes", "计划执行时间": "planned_execution_time",
                "附件": "attachment", "软件版本": "software_version",
            },
        }],
    })
    assert confirmed.status_code == 200
    return mapping["id"]


def test_mock_rc2_full_acceptance_flow(client: TestClient) -> None:
    project = _create_project(client)
    secret = "rc2-acceptance-secret"
    config = client.put("/api/ai-session-config", headers={"X-Session-ID": "rc2-mock-acceptance"}, json={
        "provider": "custom", "model": "acceptance-model", "base_url": "https://example.invalid",
        "api_key": secret,
    })
    assert config.status_code == 200 and secret not in config.text
    version = _prepare_version(client, project["id"])
    analysis = client.post(
        f"/api/projects/{project['id']}/requirement-versions/{version['id']}/requirement-review",
        json={"mode": "mock"},
    )
    assert analysis.status_code == 201
    review = analysis.json()
    assert review["is_mock"] is True
    assert {item["source_reference"]["filename"] for item in review["atomic_requirements"]} == {
        "SRS.md", "implementation-spec.md",
    }
    conflict = client.get(f"/api/projects/{project['id']}/requirement-reviews/{review['id']}/conflicts").json()[0]
    resolved = client.patch(
        f"/api/projects/{project['id']}/requirement-reviews/{review['id']}/conflicts/{conflict['conflict_id']}",
        json={"decision": "srs_preferred", "confirmer_name": "测试工程师", "decision_note": "以 SRS 为准"},
    )
    assert resolved.status_code == 200
    confirmed_review = _confirm_requirements(client, project["id"], resolved.json())
    design = client.post(
        f"/api/projects/{project['id']}/requirement-versions/{version['id']}/test-designs",
        json={"dimension_names": ["功能"]},
    )
    assert design.status_code == 201
    design_confirmed = client.post(
        f"/api/projects/{project['id']}/test-designs/{design.json()['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    assert design_confirmed.status_code == 200
    mapping_id = _confirm_template(client, project["id"])
    generation = client.post(
        f"/api/projects/{project['id']}/test-designs/{design.json()['id']}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal"], "accept_template_limitations": True},
    )
    assert generation.status_code == 201, generation.text
    generated = generation.json()
    assert generated["is_mock"] is True and generated["candidates"]
    batch = client.post(
        f"/api/projects/{project['id']}/case-generations/{generated['id']}/reviews", json={}
    ).json()
    candidate_id = batch["suggestions"][0]["candidate_id"]
    edited = client.patch(
        f"/api/projects/{project['id']}/case-review-batches/{batch['id']}/cases/{candidate_id}",
        json={"title": "人工验收标题", "reason": "确认用例内容"},
    )
    assert edited.status_code == 200 and edited.json()["revisions"][-1]["manual_modified"] is True
    for suggestion in batch["suggestions"]:
        response = client.patch(
            f"/api/projects/{project['id']}/case-review-batches/{batch['id']}/suggestions/{suggestion['id']}",
            json={"decision": "accepted", "reason": "验收确认"},
        )
        assert response.status_code == 200
    inclusion = {candidate["id"]: True for candidate in generated["candidates"]}
    confirmed_response = client.post(
        f"/api/projects/{project['id']}/case-review-batches/{batch['id']}/confirm",
        json={"confirmer_name": "测试工程师", "inclusion": inclusion},
    )
    assert confirmed_response.status_code == 200, confirmed_response.text
    confirmed_batch = confirmed_response.json()
    confirmed_revision = next(
        item for item in reversed(confirmed_batch["revisions"]) if item["candidate_id"] == candidate_id
    )
    stable_case_id = confirmed_revision["stable_case_id"]
    assert confirmed_revision["candidate"]["title"] == "人工验收标题"
    restored = client.patch(
        f"/api/projects/{project['id']}/case-review-batches/{batch['id']}/cases/{stable_case_id}",
        json={"restore_original": True, "reason": "恢复模型结果"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["revisions"][-1]["candidate"]["title"] != "人工验收标题"
    removed = client.patch(
        f"/api/projects/{project['id']}/case-review-batches/{batch['id']}/cases/{stable_case_id}/status",
        json={"participation_status": "not_included", "reason": "暂不纳入本轮", "confirmer_name": "测试工程师"},
    )
    assert removed.status_code == 200
    recovered = client.patch(
        f"/api/projects/{project['id']}/case-review-batches/{batch['id']}/cases/{stable_case_id}/status",
        json={"participation_status": "included", "reason": "恢复纳入", "confirmer_name": "测试工程师"},
    )
    assert recovered.status_code == 200
    exported = client.post(
        f"/api/projects/{project['id']}/case-review-batches/{batch['id']}/export", json={"scope": "all"}
    )
    assert exported.status_code == 200
    rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert len(rows[0]) == 16 and "父记录" not in rows[0] and rows[1][15] == "v2.0.0"
    assert secret not in exported.text
    audit = client.get(f"/api/projects/{project['id']}/ai-runs/audit-export")
    assert audit.status_code == 200 and "api_key" not in audit.text.lower() and secret not in audit.text
    for report_type in ("test-design", "execution-governance", "audit-package"):
        report = client.get(f"/api/projects/{project['id']}/reports/{report_type}")
        assert report.status_code == 200 and "api_key" not in report.text.lower() and secret not in report.text
        download = client.get(f"/api/projects/{project['id']}/reports/{report_type}/download")
        assert download.status_code == 200 and secret not in download.text
    assert confirmed_review["status"] == "confirmed"


@pytest.mark.skipif(
    not all(
        os.getenv(name)
        for name in ("RC2_REAL_MODEL_BASE_URL", "RC2_REAL_MODEL_API_KEY", "RC2_REAL_MODEL_NAME")
    ),
    reason="设置 RC2_REAL_MODEL_BASE_URL、RC2_REAL_MODEL_API_KEY、RC2_REAL_MODEL_NAME 后运行真实模型验收",
)
def test_real_model_requirement_analysis_acceptance(client: TestClient) -> None:
    project = _create_project(client)
    files = [
        _register_requirement(client, project["id"], "SRS.md", "设备应返回当前状态。"),
        _register_requirement(client, project["id"], "implementation-spec.md", "状态响应必须包含时间戳。"),
    ]
    package = client.post(f"/api/projects/{project['id']}/requirement-packages", json={"files": files}).json()
    version = client.post(
        f"/api/projects/{project['id']}/requirement-packages/{package['id']}/publish"
    ).json()
    session_id = "rc2-real-model-acceptance"
    config = client.put("/api/ai-session-config", headers={"X-Session-ID": session_id}, json={
        "provider": "custom", "model": os.environ["RC2_REAL_MODEL_NAME"],
        "base_url": os.environ["RC2_REAL_MODEL_BASE_URL"], "api_key": os.environ["RC2_REAL_MODEL_API_KEY"],
    })
    assert config.status_code == 200 and "api_key" not in config.text.lower()
    analysis = client.post(
        f"/api/projects/{project['id']}/requirement-versions/{version['id']}/requirement-review",
        headers={"X-Session-ID": session_id}, json={"mode": "real"},
    )
    assert analysis.status_code == 201, analysis.text
    assert analysis.json()["is_mock"] is False
    assert analysis.json()["requirements"]
    assert all(item["source_references"] for item in analysis.json()["requirements"])
    audit = client.get(f"/api/projects/{project['id']}/ai-runs/audit-export")
    assert os.environ["RC2_REAL_MODEL_API_KEY"] not in audit.text
