from fastapi.testclient import TestClient


def create_project(client: TestClient, name: str = "智能采集设备测试设计") -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "test_object": "虚构智能采集设备",
            "software_version": "v1.0.0",
            "description": "验证通用采集与异常恢复能力。",
            "settings": {"requirement_language": "zh-CN"},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_engineer_can_create_and_read_a_test_design_project(client: TestClient) -> None:
    created = create_project(client)

    response = client.get(f"/api/projects/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created
    assert created["settings"] == {"requirement_language": "zh-CN"}


def test_project_list_distinguishes_multiple_test_design_projects(client: TestClient) -> None:
    first = create_project(client, "接口服务测试设计")
    second = create_project(client, "Web 系统测试设计")

    response = client.get("/api/projects")

    assert response.status_code == 200
    assert [project["id"] for project in response.json()] == [second["id"], first["id"]]


def test_engineer_can_edit_a_test_design_project(client: TestClient) -> None:
    created = create_project(client)

    response = client.put(
        f"/api/projects/{created['id']}",
        json={
            "name": "智能采集设备 V1 测试设计",
            "test_object": "虚构智能采集设备 V1",
            "software_version": "v1.0.1",
            "description": "更新后的项目边界。",
            "settings": {"requirement_language": "en-US"},
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "智能采集设备 V1 测试设计"
    assert response.json()["settings"] == {"requirement_language": "en-US"}


def test_invalid_project_input_returns_clear_validation_errors(client: TestClient) -> None:
    response = client.post(
        "/api/projects",
        json={
            "name": "   ",
            "test_object": "",
            "software_version": "",
            "description": "",
            "settings": {"requirement_language": "unsupported"},
        },
    )

    assert response.status_code == 422
    fields = {error["loc"][-1] for error in response.json()["detail"]}
    assert fields == {"name", "test_object", "software_version", "requirement_language"}


def test_missing_project_returns_not_found(client: TestClient) -> None:
    read_response = client.get("/api/projects/999")
    update_response = client.put(
        "/api/projects/999",
        json={
            "name": "不存在的项目",
            "test_object": "虚构对象",
            "software_version": "v1.0.0",
            "description": "",
            "settings": {"requirement_language": "zh-CN"},
        },
    )

    assert read_response.status_code == 404
    assert read_response.json() == {"detail": "测试设计项目不存在"}
    assert update_response.status_code == 404


def test_project_persists_when_application_restarts(tmp_path) -> None:
    from app.main import create_app

    database_path = tmp_path / "persistent.db"
    with TestClient(create_app(database_path)) as first_client:
        created = create_project(first_client)

    with TestClient(create_app(database_path)) as restarted_client:
        response = restarted_client.get(f"/api/projects/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == created["name"]
