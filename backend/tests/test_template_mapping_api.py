import base64
import io
import zipfile

from fastapi.testclient import TestClient


def _project(client: TestClient) -> int:
    response = client.post(
        "/api/projects",
        json={
            "name": "模板映射项目", "test_object": "虚构智能采集设备", "description": "模板边界",
            "settings": {"requirement_language": "zh-CN"},
        },
    )
    return response.json()["id"]


def _xlsx() -> str:
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>
      <sheet name="用例" sheetId="1" r:id="rId1"/><sheet name="说明" sheetId="2" r:id="rId2"/>
    </sheets></workbook>'''.encode()
    rels = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
      <Relationship Id="rId2" Target="worksheets/sheet2.xml"/>
    </Relationships>'''.encode()
    sheet1 = '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
      <row r="1"><c r="A1" t="inlineStr"><is><t>用例编号</t></is></c><c r="B1" t="inlineStr"><is><t>用例标题</t></is></c>
      <c r="C1" t="inlineStr"><is><t>测试步骤</t></is></c><c r="D1" t="inlineStr"><is><t>预期结果</t></is></c></row>
    </sheetData></worksheet>'''.encode()
    sheet2 = '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
      <row r="1"><c r="A1" t="inlineStr"><is><t>说明</t></is></c><c r="B1" t="inlineStr"><is><t>内容</t></is></c></row>
    </sheetData></worksheet>'''.encode()
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet1)
        archive.writestr("xl/worksheets/sheet2.xml", sheet2)
    return base64.b64encode(result.getvalue()).decode()


def test_xlsx_inventory_mapping_validation_and_round_trip(client: TestClient) -> None:
    project_id = _project(client)
    workbook_base64 = _xlsx()
    uploaded = client.post(
        f"/api/projects/{project_id}/template-mappings",
        json={"filename": "用例模板.xlsx", "content_base64": workbook_base64},
    )
    assert uploaded.status_code == 201
    mapping = uploaded.json()
    assert mapping["format"] == "xlsx"
    assert [sheet["name"] for sheet in mapping["sheets"]] == ["用例", "说明"]
    assert mapping["sheets"][0]["role_suggestion"] == "case"
    assert mapping["sheets"][0]["title_row_candidates"] == [1]

    selections = [
        {"sheet_name": "用例", "role": "case", "participates": True, "title_row": 1,
         "field_mapping": {
             "用例编号": "external_case_number", "用例标题": "title", "测试步骤": "steps",
             "预期结果": "overall_expectation",
         }},
        {"sheet_name": "说明", "role": "instruction", "participates": False, "title_row": 1, "field_mapping": {}},
    ]
    confirmed = client.post(
        f"/api/projects/{project_id}/template-mappings/{mapping['id']}/confirm",
        json={"confirmer_name": "测试工程师", "mappings": selections},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    exported = client.get(f"/api/projects/{project_id}/template-mappings/{mapping['id']}/export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert archive.read("xl/workbook.xml")
        assert archive.read("xl/worksheets/sheet1.xml")
    repeated = client.post(
        f"/api/projects/{project_id}/template-mappings/{mapping['id']}/confirm",
        json={"confirmer_name": "测试工程师", "mappings": selections},
    )
    assert repeated.status_code == 409


def test_csv_uses_same_flow_and_reports_duplicate_mapping(client: TestClient) -> None:
    project_id = _project(client)
    uploaded = client.post(
        f"/api/projects/{project_id}/template-mappings",
        json={"filename": "用例.csv", "content_base64": base64.b64encode("标题,步骤,预期结果\n".encode()).decode()},
    )
    assert uploaded.status_code == 201
    sheet = uploaded.json()["sheets"][0]
    validation = client.post(
        f"/api/projects/{project_id}/template-mappings/{uploaded.json()['id']}/validate",
        json={"confirmer_name": "测试工程师", "mappings": [{
            "sheet_name": "CSV", "role": "case", "participates": True, "title_row": 1,
            "field_mapping": {"标题": "title", "步骤": "steps", "预期结果": "steps"},
        }]},
    )
    assert validation.status_code == 200
    codes = {item["code"] for item in validation.json()["diagnostics"]}
    assert "duplicate_mapping" in codes
    assert sheet["name"] == "CSV"


def test_new_upload_gets_new_template_version(client: TestClient) -> None:
    project_id = _project(client)
    payload = {"filename": "用例.csv", "content_base64": base64.b64encode("标题,步骤,预期结果\n".encode()).decode()}
    first = client.post(f"/api/projects/{project_id}/template-mappings", json=payload).json()
    second = client.post(f"/api/projects/{project_id}/template-mappings", json=payload).json()
    assert (first["version"], second["version"]) == (1, 2)
    assert len(client.get(f"/api/projects/{project_id}/template-mappings").json()) == 2
