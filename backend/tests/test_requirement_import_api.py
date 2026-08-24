import base64

from fastapi.testclient import TestClient


def encoded(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def create_project(client: TestClient) -> int:
    response = client.post(
        "/api/projects",
        json={
            "name": "结构化需求导入项目",
            "test_object": "虚构智能采集设备",
            "description": "验证需求资料导入。",
            "settings": {"requirement_language": "zh-CN"},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def register_asset(client: TestClient, project_id: int, name: str, content: bytes) -> int:
    response = client.post(
        f"/api/projects/{project_id}/assets",
        json={
            "name": name,
            "asset_type": "requirement_material",
            "provenance_kind": "original_synthetic",
            "source": "测试工程师从零创作",
            "usage_permission": "project_owned",
            "model_permission": "allowed",
            "requirement_version": "待发布",
            "purpose": "结构化需求导入",
            "content_base64": encoded(content),
            "change_reason": "首次登记",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def import_file(
    client: TestClient,
    project_id: int,
    name: str,
    content: bytes,
    media_type: str = "text/plain",
) -> dict:
    asset_id = register_asset(client, project_id, name, content)
    return {
        "asset_id": asset_id,
        "filename": name,
        "media_type": media_type,
        "content_base64": encoded(content),
    }


def test_supported_structured_files_form_one_reviewable_requirement_package(client: TestClient) -> None:
    project_id = create_project(client)
    files = [
        import_file(client, project_id, "overview.md", b"# Overview\n\nCollect status.\n"),
        import_file(client, project_id, "rules.txt", "必须保留原始状态。".encode()),
        import_file(client, project_id, "rules.json", b'{"retry": {"limit": 2}}', "application/json"),
        import_file(client, project_id, "limits.yaml", b"storage:\n  minimum_gb: 8\n", "application/yaml"),
        import_file(
            client,
            project_id,
            "openapi.yaml",
            b"openapi: 3.1.0\ninfo:\n  title: Synthetic API\n  version: '1'\npaths:\n  /status:\n    get: {}\n",
            "application/yaml",
        ),
    ]

    response = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "V1 结构化需求资料包", "files": files},
    )

    assert response.status_code == 201
    package = response.json()
    assert package["status"] == "draft"
    assert [item["format"] for item in package["materials"]] == [
        "markdown",
        "text",
        "json",
        "yaml",
        "openapi",
    ]
    assert all(item["parse_status"] == "complete" for item in package["materials"])
    assert package["diagnostics"] == []
    assert package["materials"][0]["fragments"][0]["source_reference"]["locator"] == "lines:1-1"
    assert package["materials"][2]["fragments"][0]["source_reference"]["locator"] == "/retry/limit"
    assert package["materials"][4]["fragments"][0]["source_reference"]["locator"] == "/info/title"

    read_response = client.get(f"/api/projects/{project_id}/requirement-packages/{package['id']}")
    assert read_response.status_code == 200
    assert read_response.json() == package


def test_partial_failure_and_unsafe_assets_return_explicit_diagnostics(client: TestClient) -> None:
    project_id = create_project(client)
    valid = import_file(client, project_id, "valid.txt", b"A valid requirement.")
    malformed = import_file(client, project_id, "broken.json", b'{"missing":', "application/json")
    unsupported = import_file(client, project_id, "notes.csv", b"key,value\na,b", "text/csv")
    changed = import_file(client, project_id, "changed.md", b"registered")
    changed["content_base64"] = encoded(b"different")

    response = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "包含诊断的资料包", "files": [valid, malformed, unsupported, changed]},
    )

    assert response.status_code == 201
    package = response.json()
    assert [item["parse_status"] for item in package["materials"]] == [
        "complete",
        "failed",
        "failed",
        "rejected",
    ]
    assert {item["code"] for item in package["diagnostics"]} == {
        "malformed_content",
        "unsupported_format",
        "asset_hash_mismatch",
    }
    assert all(item["message"] for item in package["diagnostics"])


def test_oversized_and_unreadable_files_are_diagnosed_without_silent_completion(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    oversized_content = b"x" * (2 * 1024 * 1024 + 1)
    oversized = import_file(client, project_id, "large.txt", oversized_content)
    unreadable = import_file(client, project_id, "binary.txt", b"\xff\xfe\x00")

    response = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "异常资料包", "files": [oversized, unreadable]},
    )

    assert response.status_code == 201
    assert [item["parse_status"] for item in response.json()["materials"]] == ["rejected", "failed"]
    assert {item["code"] for item in response.json()["diagnostics"]} == {
        "file_too_large",
        "unreadable_content",
    }


def test_partially_extractable_openapi_is_preserved_with_warning(client: TestClient) -> None:
    project_id = create_project(client)
    partial = import_file(
        client,
        project_id,
        "partial-openapi.yaml",
        b"openapi: 3.1.0\ninfo:\n  title: Metadata only\n  version: '1'\n",
        "application/yaml",
    )

    response = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "部分解析资料包", "files": [partial]},
    )

    material = response.json()["materials"][0]
    assert response.status_code == 201
    assert material["format"] == "openapi"
    assert material["parse_status"] == "partial"
    assert material["fragments"]
    assert response.json()["diagnostics"][0]["code"] == "partial_openapi"


def test_publishing_creates_immutable_requirement_versions_with_original_facts(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    first_content = b"# V1\n\nInitial behavior.\n"
    first_file = import_file(client, project_id, "requirements.md", first_content)
    first_package = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "V1 需求资料包", "files": [first_file]},
    ).json()

    first_publish = client.post(
        f"/api/projects/{project_id}/requirement-packages/{first_package['id']}/publish"
    )
    repeated_publish = client.post(
        f"/api/projects/{project_id}/requirement-packages/{first_package['id']}/publish"
    )

    assert first_publish.status_code == 201
    assert repeated_publish.status_code == 409
    version_one = first_publish.json()
    assert version_one["version"] == 1
    assert version_one["materials"][0]["content_base64"] == encoded(first_content)
    assert version_one["materials"][0]["sha256"]

    second_content = b"# V2\n\nUpdated behavior.\n"
    second_file = import_file(client, project_id, "requirements.md", second_content)
    second_package = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "V2 需求资料包", "files": [second_file]},
    ).json()
    version_two = client.post(
        f"/api/projects/{project_id}/requirement-packages/{second_package['id']}/publish"
    ).json()

    versions = client.get(f"/api/projects/{project_id}/requirement-versions")
    unchanged_v1 = client.get(f"/api/projects/{project_id}/requirement-versions/{version_one['id']}")
    assert versions.status_code == 200
    assert [item["version"] for item in versions.json()] == [1, 2]
    assert version_two["version"] == 2
    assert unchanged_v1.json() == version_one


def test_empty_or_fully_failed_package_cannot_be_published(client: TestClient) -> None:
    project_id = create_project(client)
    broken = import_file(client, project_id, "broken.json", b"not-json", "application/json")
    package = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "无有效资料", "files": [broken]},
    ).json()

    response = client.post(
        f"/api/projects/{project_id}/requirement-packages/{package['id']}/publish"
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "需求资料包没有可发布的完整解析结果"}
