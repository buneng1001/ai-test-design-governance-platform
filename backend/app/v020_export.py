import json

from app.case_lifecycle_service import _build_xlsx
from app.requirement_repository import RequirementRepository
from app.template_service import STANDARD_FIELD_NAMES
from app.v020_contracts import DEFAULT_CASE_HEADERS, REQUIREMENT_TABLE_HEADERS, analysis_table_row
from app.v020_repository import V020Repository


EXPORT_HEADERS = {
    "analysis": ["纳入范围", *REQUIREMENT_TABLE_HEADERS],
    "suggestions": REQUIREMENT_TABLE_HEADERS,
    "review": REQUIREMENT_TABLE_HEADERS,
    "cases": DEFAULT_CASE_HEADERS,
}


def build_page_export(
    project_id: int, page: str, format_name: str,
    repository: V020Repository, requirements: RequirementRepository, run_id: str | None = None,
) -> tuple[bytes, str, str]:
    payload = _page_payload(project_id, page, repository, requirements, run_id)
    extension = "json" if format_name == "json" else "xlsx"
    filename = f"{page}-{run_id or 'result'}.{extension}"
    if format_name == "json":
        return (json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
                "application/json; charset=utf-8", filename)
    if page == "cases":
        return (_case_xlsx(payload["items"], _case_template(project_id, run_id, repository)),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename)
    headers = EXPORT_HEADERS[page]
    rows = [headers, *[_xlsx_row(page, item, index) for index, item in enumerate(payload["items"], start=1)]]
    sheets = [(_sheet_name(page), rows)]
    if page == "review" and payload.get("reports"):
        report_rows = [["审核身份", "分析摘要", "已有基础", "关注事项"]]
        report_rows.extend([
            [item["role"], item["summary"], "；".join(item.get("strengths", [])), "；".join(item.get("concerns", []))]
            for item in payload["reports"]
        ])
        sheets.insert(0, ("审核分析报告", report_rows))
    return (_build_xlsx(sheets),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename)


def _page_payload(
    project_id: int, page: str, repository: V020Repository, requirements: RequirementRepository,
    run_id: str | None,
) -> dict:
    if page == "upload":
        state = repository.workspace_row(project_id)
        version = requirements.get_version(project_id, state["active_requirement_version_id"])
        parse_result = requirements.latest_package(project_id)
        return {"supplemental_notes": state["supplemental_notes"],
                "latest_parse_result": parse_result.model_dump(mode="json") if parse_result else None,
                "requirement_version": version.model_dump(mode="json") if version else None}
    table = {
        "analysis": "v020_analysis_rows", "suggestions": "v020_suggestions",
        "review": "v020_review_suggestions", "cases": "v020_cases",
    }[page]
    items = (repository.list_payloads(table, project_id, run_id) if run_id
             else repository.active_payloads(table, project_id, page))
    if page == "cases":
        items = [item for item in items if item.get("included") and not item.get("removed")]
    if run_id:
        runs = repository.list_payloads("v020_runs", project_id, run_id)
        active_run = next((item for item in runs if item.get("page") == page), None)
    else:
        active_run = repository.latest_completed_run(project_id, page)
    return {"page": page, "run_id": run_id or (active_run or {}).get("id"), "items": items,
            "reports": (active_run or {}).get("role_reports", [])}


def _case_template(project_id: int, run_id: str | None, repository: V020Repository) -> dict:
    generations = repository.case_generations(project_id)
    if run_id is None:
        matching = repository.active_case_generations(project_id)
    else:
        matching = [item for item in generations if item["run_id"] == run_id]
    return matching[-1]["template"] if matching else {"sheets": []}


def _case_xlsx(items: list[dict], template: dict) -> bytes:
    sheets = []
    for sheet in template.get("sheets", []):
        if sheet.get("role") != "case" or not sheet.get("participates", False):
            continue
        headers = [column["name"] for column in sheet.get("columns", [])]
        field_by_header = dict(sheet.get("field_mapping", {}))
        field_by_header.update({name: field for name, field in STANDARD_FIELD_NAMES.items() if name in headers})
        rows = [headers]
        for item in items:
            values = _case_values(item)
            rows.append([str(values.get(field_by_header.get(header, ""), "")) for header in headers])
        sheets.append((sheet["name"], rows))
    if not sheets:
        default_rows = [EXPORT_HEADERS["cases"]]
        default_rows.extend(_xlsx_row("cases", item, index) for index, item in enumerate(items, start=1))
        sheets = [("测试用例", default_rows)]
    return _build_xlsx(sheets)


def _case_values(item: dict) -> dict:
    steps = item.get("steps", [])
    return {
        "external_case_number": item.get("external_case_number", item.get("id", "")), "title": item.get("title", ""),
        "objective": item.get("objective", ""), "preconditions": "；".join(item.get("preconditions", [])),
        "input": item.get("test_input", ""),
        "steps": "\n".join(f"{step.get('order')}. {step.get('action')}" for step in steps),
        "step_expectations": "\n".join(f"{step.get('order')}. {step.get('expected')}" for step in steps),
        "overall_expectation": item.get("overall_expectation", ""),
        "evidence_requirements": "；".join(item.get("evidence_requirements", [])),
        "priority": item.get("priority", ""), "test_type": item.get("test_type", ""), "module": item.get("module", ""),
        "test_item": item.get("test_item", ""), "test_result": "", "test_record": "",
        "pre_test_notes": "", "planned_execution_time": "", "attachment": item.get("attachment", ""),
        "software_version": item.get("software_version", ""),
    }


def _xlsx_row(page: str, item: dict, index: int) -> list[str]:
    if page == "analysis":
        row = analysis_table_row(item, index)
        return ["是" if item.get("selected") else "否", *row.values()]
    if page in {"suggestions", "review"}:
        return list(analysis_table_row(item, index).values())
    values = _case_values(item)
    return [str(values.get(STANDARD_FIELD_NAMES[header], "")) for header in DEFAULT_CASE_HEADERS]


def _sheet_name(page: str) -> str:
    return {"analysis": "需求分析", "suggestions": "新增建议", "review": "审核报告", "cases": "测试用例"}[page]
