import io
import json
import zipfile
from typing import Any

from app.project_repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.case_lifecycle_service import default_template
from app.template_repository import TemplateMappingRepository
from app.v020_repository import V020Repository


def build_delivery_package(
    project_id: int,
    projects: ProjectRepository,
    requirements: RequirementRepository,
    workspace: V020Repository,
    templates: TemplateMappingRepository,
) -> bytes:
    project = projects.get(project_id)
    if project is None:
        raise ValueError("测试设计项目不存在")
    state = workspace.workspace_row(project_id)
    version = requirements.get_version(project_id, state["active_requirement_version_id"])
    parse_result = requirements.latest_package(project_id)
    runs = workspace.list_payloads("v020_runs", project_id)
    analysis_rows = workspace.list_payloads("v020_analysis_rows", project_id)
    suggestions = workspace.list_payloads("v020_suggestions", project_id)
    reviews = workspace.list_payloads("v020_review_suggestions", project_id)
    cases = workspace.list_payloads("v020_cases", project_id)
    generations = workspace.case_generations(project_id)
    exports = workspace.export_history(project_id)
    if state["template_mode"] == "uploaded" and state["template_mapping_id"]:
        mapping = templates.get(project_id, state["template_mapping_id"])
    else:
        mapping, _ = default_template(project_id)
    manifest = {
        "product_name": "AI 测试用例生成平台",
        "project": project.model_dump(mode="json"),
        "steps": {
            "upload": {"status": "已解析" if version else "未执行"},
            "analysis": {"status": _page_status(runs, "analysis")},
            "suggestions": {"status": _page_status(runs, "suggestions")},
            "review": {"status": _page_status(runs, "review")},
            "cases": {"status": _page_status(runs, "cases")},
        },
        "download_count": len(exports),
        "security": "项目交付包不包含 API Key 或明文模型凭据。",
    }
    files: dict[str, Any] = {
        "manifest.json": manifest,
        "01-upload/parse-result.json": {
            "supplemental_notes": state["supplemental_notes"],
            "latest_parse_result": parse_result.model_dump(mode="json") if parse_result else None,
            "requirement_version": version.model_dump(mode="json") if version else None,
        },
        "02-analysis/analysis.json": {"runs": _page_runs(runs, "analysis"), "rows": analysis_rows},
        "03-suggestions/suggestions.json": {"runs": _page_runs(runs, "suggestions"), "items": suggestions},
        "04-review/review.json": {"runs": _page_runs(runs, "review"), "items": reviews},
        "05-cases/cases.json": {
            "runs": _page_runs(runs, "cases"), "generations": generations, "items": cases,
            "selected_template": {
                "mode": state["template_mode"], "mapping_id": state["template_mapping_id"],
            },
        },
        "05-cases/template-mapping.json": mapping.model_dump(mode="json") if mapping else None,
        "exports/export-history.json": exports,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, payload in files.items():
            archive.writestr(filename, json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return output.getvalue()


def _page_runs(runs: list[dict], page: str) -> list[dict]:
    return [run for run in runs if run.get("page") == page]


def _page_status(runs: list[dict], page: str) -> str:
    selected = _page_runs(runs, page)
    if not selected:
        return "未执行"
    return {"completed": "已完成", "running": "正在执行", "failed": "失败"}.get(
        selected[-1].get("status", ""), "未执行"
    )
