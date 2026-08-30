import base64
import csv
import io
import zipfile
from xml.etree import ElementTree

from app.template_schemas import (
    SheetRole,
    TemplateColumn,
    TemplateDiagnostic,
    TemplateSheet,
    TemplateValidationResult,
)

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REQUIRED_FIELDS = {"title", "steps", "overall_expectation"}
FIELD_ALIASES = {
    "用例编号": "external_case_number", "case_number": "external_case_number", "编号": "external_case_number",
    "用例标题": "title", "测试标题": "title", "title": "title", "测试目标": "title",
    "前置条件": "preconditions", "precondition": "preconditions",
    "测试步骤": "steps", "步骤": "steps", "steps": "steps",
    "逐步预期": "step_expectations", "步骤预期": "step_expectations",
    "预期结果": "overall_expectation", "整体预期": "overall_expectation", "expected_result": "overall_expectation",
    "优先级": "priority", "priority": "priority", "证据要求": "evidence_requirements",
    "输入": "input", "测试类型": "test_type", "模块": "module", "测试项": "test_item",
    "测试结果": "test_result", "测试记录": "test_record", "测试前备注信息": "pre_test_notes",
    "计划执行时间": "planned_execution_time", "附件": "attachment", "软件版本": "software_version",
}
STANDARD_FIELD_NAMES = {
    "用例编号": "external_case_number", "测试用例标题": "title", "优先级": "priority", "预置条件": "preconditions",
    "输入": "input", "操作步骤": "steps", "预期结果": "step_expectations", "测试类型": "test_type",
    "模块": "module", "测试项": "test_item", "测试结果": "test_result", "测试记录": "test_record",
    "测试前备注信息": "pre_test_notes", "计划执行时间": "planned_execution_time", "附件": "attachment",
    "软件版本": "software_version",
}


def inspect_template(filename: str, content_base64: str) -> tuple[str, list[TemplateSheet], list[TemplateDiagnostic]]:
    try:
        content = base64.b64decode(content_base64, validate=True)
    except ValueError as error:
        raise ValueError("模板文件不是有效的 Base64 内容") from error
    if filename.lower().endswith(".csv"):
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
        return "csv", [_inspect_sheet("CSV", 0, rows)], []
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("仅支持 XLSX 或 CSV 用例模板")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            sheets = _xlsx_sheets(workbook)
            diagnostics = _complexity_diagnostics(workbook)
            return "xlsx", [
                _inspect_sheet(name, index, _xlsx_rows(workbook, path))
                for index, (name, path) in enumerate(sheets)
            ], diagnostics
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError) as error:
        raise ValueError("XLSX 工作簿无法读取") from error


def validate_mappings(sheets: list[TemplateSheet]) -> TemplateValidationResult:
    diagnostics: list[TemplateDiagnostic] = []
    case_sheets = [sheet for sheet in sheets if sheet.role == "case" and sheet.participates]
    if not case_sheets:
        diagnostics.append(TemplateDiagnostic(code="no_case_sheet", severity="error", message="至少确认一张参与处理的用例表"))
    for sheet in sheets:
        if not sheet.participates:
            continue
        if sheet.title_row is None or not sheet.field_mapping:
            diagnostics.append(TemplateDiagnostic(
                code="mapping_incomplete", severity="error", message="参与处理的工作表必须确认标题行和模板映射", sheet_name=sheet.name,
            ))
            continue
        values = list(sheet.field_mapping.values())
        duplicates = sorted({value for value in values if values.count(value) > 1})
        diagnostics.extend(
            TemplateDiagnostic(
                code="duplicate_mapping", severity="error", message=f"字段重复映射：{value}", sheet_name=sheet.name
            )
            for value in duplicates
        )
        missing = sorted(REQUIRED_FIELDS - set(values))
        diagnostics.extend(
            TemplateDiagnostic(
                code="missing_required_field", severity="error", message=f"缺少必需字段：{field}", sheet_name=sheet.name
            )
            for field in missing
        )
        known = set(FIELD_ALIASES.values()) | REQUIRED_FIELDS
        diagnostics.extend(
            TemplateDiagnostic(
                code="unsupported_semantics", severity="warning", message=f"无法表达内部语义：{field}", sheet_name=sheet.name
            )
            for field in values if field not in known
        )
        if sheet.role != "case":
            diagnostics.append(TemplateDiagnostic(
                code="non_case_sheet_selected", severity="warning",
                message="只有工作表角色为用例表时才会参与用例处理", sheet_name=sheet.name,
            ))
    return TemplateValidationResult(
        valid=not any(item.severity == "error" for item in diagnostics), diagnostics=diagnostics
    )


def suggested_mapping(sheet: TemplateSheet) -> dict[str, str]:
    return {
        column.name: FIELD_ALIASES[column.name.strip().lower()]
        for column in sheet.columns
        if column.name.strip().lower() in FIELD_ALIASES
    }


def _inspect_sheet(name: str, index: int, rows: list[list[str]]) -> TemplateSheet:
    candidates = [
        row_number for row_number, row in enumerate(rows[:20], start=1)
        if len([cell for cell in row if cell.strip()]) >= 2
    ]
    title_row = candidates[0] if candidates else None
    headers = rows[title_row - 1] if title_row else []
    columns = [
        TemplateColumn(
            index=index + 1,
            name=value.strip(),
            sample_values=[
                row[index].strip() for row in rows[title_row: title_row + 3]
                if len(row) > index and row[index].strip()
            ],
        )
        for index, value in enumerate(headers) if value.strip() and value.strip() != "父记录"
    ]
    role = _suggest_role(name, [column.name for column in columns])
    return TemplateSheet(
        name=name, index=index, role_suggestion=role, title_row_candidates=candidates, columns=columns,
        diagnostics=[] if title_row else [TemplateDiagnostic(
            code="title_row_not_found", severity="warning", message="未找到候选标题行", sheet_name=name
        )],
    )


def _suggest_role(name: str, headers: list[str]) -> SheetRole:
    text = f"{name} {' '.join(headers)}".lower()
    if any(token in text for token in ("说明", "instruction", "readme")):
        return "instruction"
    if any(token in text for token in ("字典", "dictionary", "枚举")):
        return "dictionary"
    if any(token in text for token in ("统计", "summary", "count")):
        return "statistics"
    if any(FIELD_ALIASES.get(header.strip().lower()) == "title" for header in headers):
        return "case"
    return "unknown"


def _xlsx_sheets(workbook: zipfile.ZipFile) -> list[tuple[str, str]]:
    root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    relationships = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rels = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
    result = []
    relationship_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for item in root.findall("main:sheets/main:sheet", NS):
        target = rels[item.attrib[relationship_key]].lstrip("/")
        result.append((item.attrib["name"], "xl/" + target))
    return result


def _xlsx_rows(workbook: zipfile.ZipFile, path: str) -> list[list[str]]:
    shared = []
    if "xl/sharedStrings.xml" in workbook.namelist():
        shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        shared = [
            "".join(node.text or "" for node in item.findall(".//main:t", NS))
            for item in shared_root.findall("main:si", NS)
        ]
    root = ElementTree.fromstring(workbook.read(path))
    rows: list[list[str]] = []
    for row in root.findall("main:sheetData/main:row", NS):
        values: list[str] = []
        for cell in row.findall("main:c", NS):
            ref = cell.attrib.get("r", "A1")
            index = _column_index(ref)
            while len(values) <= index:
                values.append("")
            value = cell.find("main:v", NS)
            text = value.text if value is not None and value.text else ""
            if cell.attrib.get("t") == "s" and text.isdigit() and int(text) < len(shared):
                text = shared[int(text)]
            inline = cell.find("main:is/main:t", NS)
            if inline is not None:
                text = inline.text or ""
            values[index] = text
        rows.append(values)
    return rows


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    return sum(
        (ord(character.upper()) - 64) * 26 ** position
        for position, character in enumerate(reversed(letters))
    ) - 1


def _complexity_diagnostics(workbook: zipfile.ZipFile) -> list[TemplateDiagnostic]:
    names = set(workbook.namelist())
    checks = [
        ("formula_loss", "warning", "工作簿包含公式，导出时可能只保留计算结果", any(
            name.endswith(".xml") and b"<f" in workbook.read(name) for name in names if name.endswith(".xml")
        )),
        ("macro_loss", "error", "工作簿包含宏，当前边界不保证保留宏", "xl/vbaProject.bin" in names),
        ("image_loss", "warning", "工作簿包含图片，当前边界不保证保留图片", any(
            name.startswith("xl/media/") for name in names
        )),
        ("merged_cells", "warning", "工作簿包含合并单元格，映射结果可能有格式损失", any(
            name.endswith(".xml") and b"<mergeCells" in workbook.read(name)
            for name in names if name.endswith(".xml")
        )),
        ("pivot_loss", "warning", "工作簿包含数据透视表，当前边界不保证保留透视行为", any(
            name.startswith("xl/pivot") for name in names
        )),
    ]
    return [
        TemplateDiagnostic(code=code, severity=severity, message=message)
        for code, severity, message, found in checks if found
    ]
