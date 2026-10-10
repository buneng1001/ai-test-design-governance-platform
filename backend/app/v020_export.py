import json

from app.case_lifecycle_service import _build_xlsx
from app.requirement_repository import RequirementRepository
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
        return {"supplemental_notes": state["supplemental_notes"],
                "requirement_version": version.model_dump(mode="json") if version else None}
    table = {
        "analysis": "v020_analysis_rows", "suggestions": "v020_suggestions",
        "review": "v020_review_suggestions", "cases": "v020_cases",
    }[page]
    return {"page": page, "run_id": run_id, "items": repository.list_payloads(table, project_id, run_id)}


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
