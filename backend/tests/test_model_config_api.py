def test_model_provider_catalog_and_session_config_do_not_return_api_key(client) -> None:
    providers = client.get("/api/model-providers")
    assert providers.status_code == 200
    assert [item["id"] for item in providers.json()] == ["deepseek", "siliconflow", "kimi", "glm", "custom"]

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


def test_custom_provider_connection_validation_is_session_only(client) -> None:
    response = client.post(
        "/api/ai-session-config/test",
        json={"provider": "custom", "model": "my-model", "base_url": "not-a-url", "api_key": "secret"},
        headers={"X-Session-ID": "test-session"},
    )
    assert response.status_code == 422
    assert "secret" not in response.text


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
