import base64
import struct
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient


def encoded(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def create_project(client: TestClient) -> int:
    response = client.post(
        "/api/projects",
        json={"name": "文档格式导入项目", "test_object": "虚构智能采集设备", "description": "验证文档与截图。"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def import_file(client: TestClient, project_id: int, name: str, content: bytes, media_type: str) -> dict:
    asset = client.post(
        f"/api/projects/{project_id}/assets",
        json={
            "name": name,
            "asset_type": "requirement_material",
            "provenance_kind": "original_synthetic",
            "source": "测试工程师从零创作",
            "usage_permission": "project_owned",
            "model_permission": "allowed",
            "requirement_version": "待发布",
            "purpose": "文档格式导入",
            "content_base64": encoded(content),
            "change_reason": "首次登记",
        },
    )
    assert asset.status_code == 201
    return {
        "asset_id": asset.json()["id"],
        "filename": name,
        "media_type": media_type,
        "content_base64": encoded(content),
    }


def docx_content() -> bytes:
    document = '''<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>DOCX 正文需求</w:t></w:r></w:p>
      <w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格规则</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body>
    </w:document>'''.encode()
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document)
    return output.getvalue()


def pdf_content() -> bytes:
    return b"%PDF-1.4\n1 0 obj\nstream\nBT /F1 12 Tf (PDF requirement) Tj ET\nendstream\n%%EOF"


def png_content() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">IIBBBBB", 3, 4, 8, 2, 0, 0, 0)


def test_docx_pdf_and_image_materials_keep_sources_and_image_inference_state(client: TestClient) -> None:
    project_id = create_project(client)
    files = [
        import_file(client, project_id, "brief.docx", docx_content(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        import_file(client, project_id, "brief.pdf", pdf_content(), "application/pdf"),
        import_file(client, project_id, "screen.png", png_content(), "image/png"),
    ]
    response = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "文档与截图需求资料包", "files": files},
    )

    assert response.status_code == 201
    materials = response.json()["materials"]
    assert [item["format"] for item in materials] == ["docx", "pdf", "png"]
    assert materials[0]["fragments"][0]["source_reference"]["locator"] == "paragraph:1"
    assert materials[0]["fragments"][1]["source_reference"]["locator"] == "table:1:row:1:cell:1"
    assert materials[1]["fragments"][0]["text"] == "PDF requirement"
    assert materials[2]["fragments"] == []
    assert materials[2]["visual_inferences"][0]["status"] == "pending_confirmation"
    assert materials[2]["visual_inferences"][0]["source_reference"]["locator"] == "image:original"


def test_document_diagnostics_cover_corrupt_empty_and_encrypted_pdf(client: TestClient) -> None:
    project_id = create_project(client)
    files = [
        import_file(client, project_id, "broken.docx", b"not-a-docx", "application/octet-stream"),
        import_file(client, project_id, "scan.pdf", b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj", "application/pdf"),
        import_file(client, project_id, "locked.pdf", b"%PDF-1.4\n/Encrypt 3 0 R", "application/pdf"),
        import_file(client, project_id, "empty.png", b"\x89PNG\r\n\x1a\n", "image/png"),
    ]
    response = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "文档诊断资料包", "files": files},
    )

    assert response.status_code == 201
    diagnostics = response.json()["diagnostics"]
    assert {item["code"] for item in diagnostics} == {
        "malformed_content", "no_extractable_text", "encrypted_pdf",
    }
    assert response.json()["materials"][1]["parse_status"] == "failed"


def test_jpg_and_partial_pdf_are_supported_with_explicit_boundaries(client: TestClient) -> None:
    project_id = create_project(client)
    jpg = b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x02\x00\x03\x01\x01\x11\x00\xff\xd9"
    partial_pdf = b"%PDF-1.4\nstream\nBT (kept text) Tj ET\nendstream\nstream\nBT bad"
    response = client.post(
        f"/api/projects/{project_id}/requirement-packages",
        json={"name": "边界格式资料包", "files": [
            import_file(client, project_id, "screen.jpg", jpg, "image/jpeg"),
            import_file(client, project_id, "partial.pdf", partial_pdf, "application/pdf"),
        ]},
    )

    assert response.status_code == 201
    materials = response.json()["materials"]
    assert materials[0]["format"] == "jpg"
    assert materials[0]["visual_inferences"][0]["description"].startswith("图片原始资产（3×2）")
    assert materials[1]["parse_status"] == "partial"
    assert materials[1]["diagnostics"][0]["code"] == "partial_pdf_text"
