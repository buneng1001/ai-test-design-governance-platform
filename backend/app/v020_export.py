import json

from app.case_lifecycle_service import _build_xlsx
from app.requirement_repository import RequirementRepository
from app.template_service import STANDARD_FIELD_NAMES
from app.v020_repository import V020Repository


EXPORT_HEADERS = {
    "analysis": ["是否勾选", "功能模块", "功能点", "测试项", "测试点", "来源", "AI 理由", "信息缺口", "状态", "生成方式"],
    "suggestions": ["类型", "优先级", "建议内容", "关联需求点", "AI 理由", "处置"],
    "review": ["审核身份", "发现类型", "建议内容", "关联需求点", "AI 理由", "处置"],
    "cases": ["是否纳入", "用例标题", "测试目标", "前置条件", "测试输入", "操作步骤", "整体预期", "优先级", "测试点 ID", "生成方式"],
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
    rows = [headers, *[_xlsx_row(page, item) for item in payload["items"]]]
    return (_build_xlsx([(_sheet_name(page), rows)]),
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
    items = repository.list_payloads(table, project_id, run_id)
    if page == "cases":
        items = [item for item in items if item.get("included") and not item.get("removed")]
    return {"page": page, "run_id": run_id, "items": items}


def _case_template(project_id: int, run_id: str | None, repository: V020Repository) -> dict:
    generations = repository.case_generations(project_id)
    matching = [item for item in generations if run_id is None or item["run_id"] == run_id]
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
        sheets = [("测试用例", [EXPORT_HEADERS["cases"], *[_xlsx_row("cases", item) for item in items]])]
    return _build_xlsx(sheets)


def _case_values(item: dict) -> dict:
    steps = item.get("steps", [])
    return {
        "external_case_number": item.get("id", ""), "title": item.get("title", ""),
        "objective": item.get("objective", ""), "preconditions": "；".join(item.get("preconditions", [])),
        "input": item.get("test_input", ""),
        "steps": "\n".join(f"{step.get('order')}. {step.get('action')}" for step in steps),
        "step_expectations": "\n".join(f"{step.get('order')}. {step.get('expected')}" for step in steps),
        "overall_expectation": item.get("overall_expectation", ""),
        "evidence_requirements": "；".join(item.get("evidence_requirements", [])),
        "priority": item.get("priority", ""), "test_type": "功能测试", "module": item.get("module", ""),
        "test_item": item.get("test_item", ""), "test_result": "", "test_record": "",
        "pre_test_notes": "", "planned_execution_time": "", "attachment": "", "software_version": "",
    }


def _xlsx_row(page: str, item: dict) -> list[str]:
    if page == "analysis":
        return [
            "是" if item.get("selected") else "否", item.get("module", ""), item.get("function_point", ""),
            item.get("test_item", ""), item.get("test_point", ""), item.get("source", ""),
            item.get("ai_reason", ""), item.get("information_gap", ""), item.get("status", ""), item.get("mode", ""),
        ]
    if page == "suggestions":
        return [item.get("suggestion_type", ""), item.get("priority", ""), item.get("content", ""),
                item.get("related_analysis_row_id", ""), item.get("ai_reason", ""), item.get("disposition", "")]
    if page == "review":
        return [item.get("role", ""), item.get("finding_type", ""), item.get("content", ""),
                item.get("related_analysis_row_id", ""), item.get("ai_reason", ""), item.get("disposition", "")]
    return [
        "是" if item.get("included") and not item.get("removed") else "否", item.get("title", ""),
        item.get("objective", ""), "；".join(item.get("preconditions", [])), item.get("test_input", ""),
        "\n".join(f"{step.get('order')}. {step.get('action')} → {step.get('expected')}" for step in item.get("steps", [])),
        item.get("overall_expectation", ""), item.get("priority", ""), item.get("analysis_row_id", ""), item.get("mode", ""),
    ]


def _sheet_name(page: str) -> str:
    return {"analysis": "需求分析", "suggestions": "新增建议", "review": "审核报告", "cases": "测试用例"}[page]
