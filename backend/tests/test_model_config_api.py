import json

from fastapi.testclient import TestClient

from app.main import create_app


def test_model_provider_catalog_and_session_config_do_not_return_api_key(client) -> None:
    providers = client.get("/api/model-providers")
    assert providers.status_code == 200
    assert [item["id"] for item in providers.json()] == ["deepseek", "siliconflow", "kimi", "glm", "custom"]
    assert providers.json()[1]["models"][0] == "Qwen/Qwen2.5-72B-Instruct"
    assert providers.json()[0]["models"] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert providers.json()[2]["models"] == ["kimi-k2.6", "kimi-k2.5", "kimi-k2.7-code"]

    payload = {
        "provider": "deepseek", "model": "deepseek-chat", "base_url": "https://api.deepseek.com",
        "api_key": "secret-key",
    }
    saved = client.put("/api/ai-session-config", json=payload, headers={"X-Session-ID": "test-session"})
    assert saved.status_code == 200
    assert saved.json() == {
        "provider": "deepseek", "model": "deepseek-chat", "base_url": "https://api.deepseek.com",
        "api_key_configured": True,
    }
    assert "secret-key" not in saved.text
    read = client.get("/api/ai-session-config", headers={"X-Session-ID": "test-session"})
    assert read.json() == saved.json()

    cleared = client.delete("/api/ai-session-config", headers={"X-Session-ID": "test-session"})
    assert cleared.status_code == 204
    assert client.get("/api/ai-session-config", headers={"X-Session-ID": "test-session"}).json() is None


def test_saved_model_config_survives_application_restart(tmp_path) -> None:
    database_path = tmp_path / "persistent-config.db"
    payload = {
        "provider": "deepseek", "model": "deepseek-chat", "base_url": "https://api.deepseek.com",
        "api_key": "secret-key",
    }
    with TestClient(create_app(database_path)) as first_app:
        saved = first_app.put("/api/ai-session-config", json=payload, headers={"X-Session-ID": "persistent-client"})
        assert saved.status_code == 200
    with TestClient(create_app(database_path)) as restarted_app:
        restored = restarted_app.get("/api/ai-session-config", headers={"X-Session-ID": "persistent-client"})
        assert restored.status_code == 200
        assert restored.json() == {
            "provider": "deepseek", "model": "deepseek-chat", "base_url": "https://api.deepseek.com",
            "api_key_configured": True,
        }
        assert "secret-key" not in restored.text


def test_custom_provider_connection_validation_is_session_only(client) -> None:
    response = client.post(
        "/api/ai-session-config/test",
        json={"provider": "custom", "model": "my-model", "base_url": "not-a-url", "api_key": "secret"},
        headers={"X-Session-ID": "test-session"},
    )
    assert response.status_code == 422
    assert "secret" not in response.text


def test_connection_test_performs_real_chat_completion(monkeypatch, client) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"connected"}}]}'

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.model_config_api.urlopen", fake_urlopen)
    response = client.post(
        "/api/ai-session-config/test",
        json={
            "provider": "siliconflow", "model": "Qwen/Qwen2.5-72B-Instruct",
            "base_url": "https://api.siliconflow.cn/v1", "api_key": "secret",
        },
        headers={"X-Session-ID": "test-session"},
    )

    assert response.json()["success"] is True
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["method"] == "POST"
    assert captured["body"]["model"] == "Qwen/Qwen2.5-72B-Instruct"
    assert captured["body"]["messages"][-1]["content"] == "请返回连接测试 JSON。"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["authorization"] == "Bearer secret"
    assert captured["timeout"] == 120


def test_asset_record_includes_computed_file_size(client) -> None:
    import base64

    project = client.post("/api/projects", json={
        "name": "资产大小测试", "test_object": "虚构对象", "software_version": "v1.0.0",
    }).json()
    content = base64.b64encode("需求内容".encode()).decode()
    response = client.post(f"/api/projects/{project['id']}/assets", json={
        "name": "srs.md", "asset_type": "requirement_material", "provenance_kind": "original_synthetic",
        "source": "测试工程师创作", "usage_permission": "project_owned", "model_permission": "allowed",
        "requirement_version": "待发布", "purpose": "需求分析", "content_base64": content, "change_reason": "首次登记",
    })
    assert response.status_code == 201
    assert response.json()["size_bytes"] == len("需求内容".encode())
