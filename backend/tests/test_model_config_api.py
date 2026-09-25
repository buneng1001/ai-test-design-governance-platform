import sqlite3
from urllib.error import HTTPError

from fastapi.testclient import TestClient

from app.main import create_app


def payload(**overrides) -> dict:
    return {
        "provider": "deepseek", "model": "deepseek-chat", "base_url": "https://api.deepseek.com",
        "api_key": "temporary-secret", **overrides,
    }


def test_catalog_and_temporary_key_never_enter_database_or_response(client, tmp_path) -> None:
    providers = client.get("/api/model-providers")
    assert [item["id"] for item in providers.json()] == ["deepseek", "siliconflow", "kimi", "glm", "custom"]
    assert providers.json()[0]["models"][0]["state"] == "preset"

    saved = client.put("/api/ai-session-config", json=payload(), headers={"X-Session-ID": "test-session"})
    assert saved.status_code == 200
    assert saved.json()["credential_source"] == "temporary"
    assert saved.json()["credential_configured"] is True
    assert "temporary-secret" not in saved.text
    assert not (tmp_path / ".env.local").exists()
    with sqlite3.connect(tmp_path / "test-design.db") as connection:
        dumped = "".join(row[0] for row in connection.execute("SELECT config_json FROM ai_model_configs"))
    assert "temporary-secret" not in dumped


def test_provider_credentials_are_isolated_and_remembered_key_is_local_only(client, tmp_path) -> None:
    headers = {"X-Session-ID": "test-session"}
    client.put("/api/ai-session-config", json=payload(), headers=headers)
    other = client.put("/api/ai-session-config", json=payload(
        provider="kimi", model="kimi-k2.6", base_url="https://api.moonshot.cn/v1", api_key="",
    ), headers=headers)
    assert other.json()["credential_source"] == "none"

    remembered = client.put("/api/ai-session-config", json=payload(
        provider="kimi", model="kimi-k2.6", base_url="https://api.moonshot.cn/v1",
        api_key="kimi-secret", remember_api_key=True,
    ), headers=headers)
    assert remembered.json()["credential_source"] == "remembered_local"
    assert "kimi-secret" not in remembered.text
    assert (tmp_path / ".env.local").read_text(encoding="utf-8") == "KIMI_API_KEY=kimi-secret\n"


def test_discovery_is_explicit_and_persists_non_sensitive_model_state(monkeypatch, client) -> None:
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"data":[{"id":"deepseek-chat"},{"id":"deepseek-reasoner"}]}'

    captured = {}
    def fake_urlopen(request, timeout):
        captured["url"], captured["authorization"] = request.full_url, request.headers["Authorization"]
        return FakeResponse()

    monkeypatch.setattr("app.model_config_api.urlopen", fake_urlopen)
    result = client.post("/api/ai-session-config/models/discover", json=payload(),
                         headers={"X-Session-ID": "test-session"})
    assert result.json() == {
        "success": True, "provider": "deepseek",
        "models": [{"id": "deepseek-chat", "state": "discovered"},
                   {"id": "deepseek-reasoner", "state": "discovered"}], "error": None,
    }
    assert captured["url"].endswith("/models")
    assert captured["authorization"] == "Bearer temporary-secret"
    status = client.get("/api/ai-session-config", headers={"X-Session-ID": "test-session"}).json()
    assert any(item == {"id": "deepseek-reasoner", "state": "discovered"} for item in status["model_options"])


def test_connection_test_persists_non_sensitive_verification_and_invalidates_on_key_change(monkeypatch, client) -> None:
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"{\\\"connected\\\":true}"}}]}'

    monkeypatch.setattr("app.model_config_api.urlopen", lambda *_, **__: FakeResponse())
    headers = {"X-Session-ID": "test-session"}
    connected = client.post("/api/ai-session-config/test", json=payload(), headers=headers)
    assert connected.json()["success"] is True
    status = client.get("/api/ai-session-config", headers=headers).json()
    assert status["verification_status"] == "verified"

    changed = client.put("/api/ai-session-config", json=payload(api_key="changed-secret"), headers=headers)
    assert changed.json()["verification_status"] == "invalidated"
    assert "changed-secret" not in changed.text


def test_connection_failure_uses_structured_redacted_error(monkeypatch, client) -> None:
    def unauthorized(*_, **__):
        raise HTTPError("https://api.deepseek.com/chat/completions", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("app.model_config_api.urlopen", unauthorized)
    result = client.post("/api/ai-session-config/test", json=payload(), headers={"X-Session-ID": "test-session"})
    assert result.json() == {
        "success": False, "message": None, "provider": "deepseek", "model": "deepseek-chat",
        "error": {
            "stage": "connection_test", "provider": "deepseek", "model": "deepseek-chat",
            "error_type": "authentication", "retryable": False,
            "user_message": "API Key 无效或没有当前模型的调用权限",
            "suggested_action": "检查该服务商的 API Key 和账号权限", "detail": "HTTP 401",
        },
    }


def test_connection_test_keeps_provider_specific_structured_output_parameters(monkeypatch, client) -> None:
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    captured = {}
    def fake_urlopen(request, **_):
        captured["body"] = request.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr("app.model_config_api.urlopen", fake_urlopen)
    result = client.post("/api/ai-session-config/test", json=payload(
        provider="siliconflow", model="deepseek-ai/DeepSeek-V3.2",
        base_url="https://api.siliconflow.cn/v1", api_key="silicon-secret",
    ), headers={"X-Session-ID": "test-session"})
    assert result.json()["success"] is True
    assert '"enable_thinking": false' in captured["body"]


def test_remembered_key_is_loaded_after_restart_without_returning_key(tmp_path) -> None:
    database_path, credentials_path = tmp_path / "config.db", tmp_path / ".env.local"
    headers = {"X-Session-ID": "persistent-client"}
    with TestClient(create_app(database_path, local_credentials_path=credentials_path)) as first_app:
        saved = first_app.put("/api/ai-session-config", json=payload(
            api_key="remembered-secret", remember_api_key=True), headers=headers)
        assert saved.json()["credential_source"] == "remembered_local"
    with TestClient(create_app(database_path, local_credentials_path=credentials_path)) as restarted_app:
        restored = restarted_app.get("/api/ai-session-config", headers=headers)
        assert restored.json()["credential_source"] == "remembered_local"
        assert "remembered-secret" not in restored.text


def test_credential_resolution_prefers_temporary_then_local_then_environment(tmp_path, monkeypatch) -> None:
    database_path, credentials_path = tmp_path / "priority.db", tmp_path / ".env.local"
    credentials_path.write_text("DEEPSEEK_API_KEY=local-secret\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-secret")
    captured: list[str] = []

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self) -> bytes: return b'{"choices":[{"message":{"content":"ok"}}]}'

    def fake_urlopen(request, **_):
        captured.append(request.headers["Authorization"])
        return FakeResponse()

    monkeypatch.setattr("app.model_config_api.urlopen", fake_urlopen)
    with TestClient(create_app(database_path, local_credentials_path=credentials_path)) as app:
        app.post("/api/ai-session-config/test", json=payload(), headers={"X-Session-ID": "temporary"})
        app.post("/api/ai-session-config/test", json=payload(api_key=""), headers={"X-Session-ID": "local"})
    credentials_path.unlink()
    with TestClient(create_app(database_path, local_credentials_path=credentials_path)) as app:
        app.post("/api/ai-session-config/test", json=payload(api_key=""), headers={"X-Session-ID": "environment"})

    assert captured == ["Bearer temporary-secret", "Bearer local-secret", "Bearer environment-secret"]
