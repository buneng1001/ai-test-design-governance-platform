import base64
import csv
import io
import zipfile
from xml.sax.saxutils import escape
from xml.etree import ElementTree

from app.case_review_schemas import CaseRevision
from app.template_service import STANDARD_FIELD_NAMES, _xlsx_rows, _xlsx_sheets
from app.template_schemas import TemplateMappingVersion, TemplateSheet

DEFAULT_HEADERS = [
    "用例编号", "测试用例标题", "优先级", "预置条件", "输入", "操作步骤", "预期结果", "测试类型",
    "模块", "测试项", "测试结果", "测试记录", "测试前备注信息", "计划执行时间", "附件", "软件版本",
]


def default_template(project_id: int) -> tuple[TemplateMappingVersion, str]:
    """返回项目默认的 16 列 XLSX 模板，不依赖用户上传文件。"""
    field_mapping = {
        header: STANDARD_FIELD_NAMES[header] for header in DEFAULT_HEADERS
    }
    sheet = TemplateSheet(
        name="用例表", index=0, role_suggestion="case", role="case", title_row_candidates=[1], title_row=1,
        columns=[{"index": index, "name": header, "sample_values": []}
                 for index, header in enumerate(DEFAULT_HEADERS, start=1)],
        participates=True, field_mapping=field_mapping,
    )
    content = _build_xlsx([("用例表", [DEFAULT_HEADERS])])
    mapping = TemplateMappingVersion(
        id=0, project_id=project_id, version=0, filename="默认测试用例模板.xlsx", format="xlsx",
        status="confirmed", sheets=[sheet], retained_sheet_names=[sheet.name], confirmed_by="系统默认模板",
    )
    return mapping, base64.b64encode(content).decode("ascii")


LIFECYCLE_TRANSITIONS = {
    "draft": {"effective", "deprecated"},
    "effective": {"closed", "deprecated", "superseded"},
    "closed": {"effective", "deprecated"},
    "deprecated": set(),
    "superseded": set(),
}


def can_change_lifecycle(current: str, target: str) -> bool:
    return current == target or target in LIFECYCLE_TRANSITIONS.get(current, set())


def latest_revisions(revisions: list[CaseRevision]) -> list[CaseRevision]:
    latest: dict[str, CaseRevision] = {}
    for revision in revisions:
        if revision.stable_case_id is None:
            continue
        previous = latest.get(revision.stable_case_id)
        if previous is None or revision.revision > previous.revision:
            latest[revision.stable_case_id] = revision
    return list(latest.values())


def select_revisions(
    revisions: list[CaseRevision], scope: str, selected_ids: list[str],
) -> list[CaseRevision]:
    current = [item for item in latest_revisions(revisions)
               if item.participation_status == "included" and item.lifecycle_status == "effective"]
    if scope == "selected":
        selected = set(selected_ids)
        return [item for item in current if item.stable_case_id in selected]
    if scope == "changed":
        return [item for item in current if item.revision > 1]
    return current


def export_template(
    mapping: TemplateMappingVersion, original_content_base64: str, revisions: list[CaseRevision],
    scope: str, selected_ids: list[str],
) -> tuple[bytes, str, str]:
    selected = select_revisions(revisions, scope, selected_ids)
    raw = base64.b64decode(original_content_base64)
    if mapping.format == "csv":
        rows = _export_rows(mapping.sheets[0], selected)
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerows(rows)
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "csv"
    with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
        rendered: dict[str, bytes] = {}
        for name, path in _xlsx_sheets(workbook):
            source = _xlsx_rows(workbook, path)
            template_sheet = next(item for item in mapping.sheets if item.name == name)
            if template_sheet.role == "case":
                rows = _export_rows(template_sheet, selected)
                rendered[path] = _render_xlsx_sheet(workbook.read(path), rows)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as result:
            for filename in workbook.namelist():
                result.writestr(filename, rendered.get(filename, workbook.read(filename)))
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"


def _export_rows(sheet: TemplateSheet, revisions: list[CaseRevision]) -> list[list[str]]:
    # 只把用例写回其唯一归属表，其他工作表使用模板原始内容保留。
    revisions = [item for item in revisions if item.candidate.case_sheet_name == sheet.name]
    headers = [column.name for column in sheet.columns]
    rows = [headers]
    field_by_header = {name: field for name, field in sheet.field_mapping.items()}
    field_by_header.update({name: field for name, field in STANDARD_FIELD_NAMES.items() if name in headers})
    for revision in revisions:
        candidate = revision.candidate
        values = {
            "external_case_number": revision.external_case_number or candidate.external_case_number or "",
            "title": candidate.title,
            "objective": candidate.objective,
            "preconditions": "；".join(candidate.preconditions),
            "steps": "\n".join(f"{step.order}. {step.action}：{step.input}" for step in candidate.steps),
            "step_expectations": "\n".join(f"{step.order}. {step.expected}" for step in candidate.steps),
            "overall_expectation": candidate.overall_expectation,
            "evidence_requirements": "；".join(candidate.evidence_requirements),
            "priority": candidate.priority,
            "input": candidate.input,
            "test_type": candidate.test_type,
            "module": candidate.module,
            "test_item": candidate.test_item,
            "test_result": candidate.test_result,
            "test_record": candidate.test_record,
            "pre_test_notes": candidate.pre_test_notes,
            "planned_execution_time": candidate.planned_execution_time,
            "attachment": candidate.attachment,
            "software_version": candidate.software_version,
        }
        rows.append([values.get(field_by_header.get(header, ""), "") for header in headers])
    return rows


def _build_xlsx(sheets: list[tuple[str, list[list[str]]]]) -> bytes:
    # 生成最小标准 XLSX，避免把平台内部字段或运行信息写入交付文件。
    files = {
        "[Content_Types].xml": _content_types(len(sheets)),
        "_rels/.rels": _rels(),
        "xl/workbook.xml": _workbook(sheets),
        "xl/_rels/workbook.xml.rels": _workbook_rels(len(sheets)),
    }
    for index, (_, rows) in enumerate(sheets, start=1):
        files[f"xl/worksheets/sheet{index}.xml"] = _worksheet(rows)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return output.getvalue()


def _content_types(count: int) -> str:
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, count + 1)
    )
    return ('<?xml version="1.0" encoding="UTF-8"?><Types '
            'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f'{overrides}</Types>')


def _rels() -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>')


def _workbook(sheets: list[tuple[str, list[list[str]]]]) -> str:
    entries = "".join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
                       for i, (name, _) in enumerate(sheets, start=1))
    return ('<?xml version="1.0" encoding="UTF-8"?><workbook '
            'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            f'{entries}</sheets></workbook>')


def _workbook_rels(count: int) -> str:
    entries = "".join(f'<Relationship Id="rId{i}" '
                       'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                       f'Target="worksheets/sheet{i}.xml"/>' for i in range(1, count + 1))
    return ('<?xml version="1.0" encoding="UTF-8"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{entries}</Relationships>')


def _worksheet(rows: list[list[str]]) -> str:
    row_xml = []
    for row_number, row in enumerate(rows, start=1):
        cells = "".join(f'<c r="{_cell_ref(index, row_number)}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                        for index, value in enumerate(row, start=1))
        row_xml.append(f'<row r="{row_number}">{cells}</row>')
    return ('<?xml version="1.0" encoding="UTF-8"?><worksheet '
            'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            f'{"".join(row_xml)}</sheetData></worksheet>')


def _cell_ref(column: int, row: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _render_xlsx_sheet(source: bytes, rows: list[list[str]]) -> bytes:
    """保留工作表结构和列样式，仅替换数据行内容。"""
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    root = ElementTree.fromstring(source)
    sheet_data = root.find(f"{{{namespace}}}sheetData")
    if sheet_data is None:
        return source
    source_rows = list(sheet_data)
    style_cells = list(source_rows[0]) if source_rows else []
    for child in list(sheet_data):
        sheet_data.remove(child)
    for row_number, values in enumerate(rows, start=1):
        row = ElementTree.Element(f"{{{namespace}}}row", {"r": str(row_number)})
        for index, value in enumerate(values, start=1):
            template = style_cells[index - 1] if index <= len(style_cells) else None
            attributes = {"r": _cell_ref(index, row_number), "t": "inlineStr"}
            if template is not None and "s" in template.attrib:
                attributes["s"] = template.attrib["s"]
            cell = ElementTree.SubElement(row, f"{{{namespace}}}c", attributes)
            inline = ElementTree.SubElement(cell, f"{{{namespace}}}is")
            text = ElementTree.SubElement(inline, f"{{{namespace}}}t")
            text.text = value
        sheet_data.append(row)
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
