import base64
import csv
import io
import zipfile
from xml.sax.saxutils import escape

from app.case_review_schemas import CaseRevision
from app.template_service import _xlsx_rows, _xlsx_sheets
from app.template_schemas import TemplateMappingVersion, TemplateSheet

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
        sheets = []
        for name, path in _xlsx_sheets(workbook):
            source = _xlsx_rows(workbook, path)
            template_sheet = next(item for item in mapping.sheets if item.name == name)
            sheets.append((name, _export_rows(template_sheet, selected) if template_sheet.role == "case"
                           else source))
    return _build_xlsx(sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"


def _export_rows(sheet: TemplateSheet, revisions: list[CaseRevision]) -> list[list[str]]:
    # 只把用例写回其唯一归属表，其他工作表使用模板原始内容保留。
    revisions = [item for item in revisions if item.candidate.case_sheet_name == sheet.name]
    headers = [column.name for column in sheet.columns]
    rows = [headers]
    reverse = {field: name for name, field in sheet.field_mapping.items()}
    for revision in revisions:
        candidate = revision.candidate
        values = {
            "external_case_number": revision.external_case_number or candidate.external_case_number or "",
            "title": candidate.title,
            "objective": candidate.objective,
            "preconditions": "；".join(candidate.preconditions),
            "steps": "；".join(f"{step.order}. {step.action}：{step.input}" for step in candidate.steps),
            "step_expectations": "；".join(f"{step.order}. {step.expected}" for step in candidate.steps),
            "overall_expectation": candidate.overall_expectation,
            "evidence_requirements": "；".join(candidate.evidence_requirements),
            "priority": candidate.priority,
        }
        rows.append([values.get(reverse.get(header, ""), "") for header in headers])
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
