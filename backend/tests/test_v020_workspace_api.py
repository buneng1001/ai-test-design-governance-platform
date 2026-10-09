import base64
import io
import json
import zipfile

from fastapi.testclient import TestClient


def _project(client: TestClient) -> dict:
    response = client.post("/api/projects", json={
        "name": "正式工作流项目",
        "test_object": "智能终端",
        "software_version": "v0.2.0",
        "description": "v0.2 正式功能验收",
        "settings": {"requirement_language": "zh-CN"},
    })
    assert response.status_code == 201
    return response.json()


def test_upload_and_parse_is_one_persisted_non_ai_operation(client: TestClient) -> None:
    project = _project(client)
    response = client.post(f"/api/v0.2/projects/{project['id']}/materials", json={
        "supplemental_notes": "重点关注状态切换；忽略历史版本章节。",
        "files": [{
            "filename": "requirements.md",
            "media_type": "text/markdown",
            "content_base64": base64.b64encode(
                "# 状态管理\n设备必须在 2 秒内完成状态切换。".encode()
            ).decode(),
        }],
    })

    assert response.status_code == 201, response.text
    uploaded = response.json()
    assert uploaded["ai_called"] is False
    assert uploaded["supplemental_notes"] == "重点关注状态切换；忽略历史版本章节。"
    assert uploaded["requirement_version"]["materials"][0]["parse_status"] == "complete"
    assert uploaded["requirement_version"]["materials"][0]["fragments"]

    restored = client.get(f"/api/v0.2/projects/{project['id']}/workspace")
    assert restored.status_code == 200
    state = restored.json()
    assert state["supplemental_notes"] == uploaded["supplemental_notes"]
    assert state["requirement_version"]["id"] == uploaded["requirement_version"]["id"]
    assert state["analysis_rows"] == []
    assert state["runs"] == []


def test_project_archive_restore_and_summary_are_persisted(client: TestClient) -> None:
    project = _project(client)

    archived = client.patch(f"/api/v0.2/projects/{project['id']}/archive", json={"archived": True})
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert client.get("/api/v0.2/projects?archived=false").json() == []
    archived_projects = client.get("/api/v0.2/projects?archived=true").json()
    assert [item["id"] for item in archived_projects] == [project["id"]]

    restored = client.patch(f"/api/v0.2/projects/{project['id']}/archive", json={"archived": False})
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    summaries = client.get("/api/v0.2/projects?archived=false").json()
    assert summaries[0]["name"] == "正式工作流项目"
    assert summaries[0]["current_requirement_version"] is None
    assert summaries[0]["latest_analysis_status"] == "尚未执行"
    assert summaries[0]["latest_case_status"] == "尚未生成"


def test_delivery_package_lists_all_pages_and_excludes_credentials(client: TestClient) -> None:
    project = _project(client)
    secret = "must-never-enter-delivery-package"
    client.put("/api/ai-session-config", headers={"X-Session-ID": "delivery-test"}, json={
        "provider": "custom",
        "model": "private-model",
        "base_url": "https://example.invalid/v1",
        "api_key": secret,
        "remember_api_key": False,
    })

    response = client.get(f"/api/v0.2/projects/{project['id']}/delivery-package")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert secret.encode() not in response.content
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert {
            "manifest.json",
            "01-upload/parse-result.json",
            "02-analysis/analysis.json",
            "03-suggestions/suggestions.json",
            "04-review/review.json",
            "05-cases/cases.json",
            "exports/export-history.json",
        }.issubset(set(archive.namelist()))
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["product_name"] == "AI 测试用例生成平台"
    assert manifest["steps"]["analysis"]["status"] == "未执行"
    assert "api_key" not in json.dumps(manifest).lower()
