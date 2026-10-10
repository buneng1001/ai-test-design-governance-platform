import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.ai_schemas import AIModelConfig
from app.ai_service import ModelRequest, ModelService
from app.case_lifecycle_service import default_template
from app.model_config_api import get_session_model_config, get_session_model_status
from app.project_repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.template_repository import TemplateMappingRepository
from app.v020_local_generation import local_analysis, local_cases, local_review, local_suggestions
from app.v020_prompts import PROMPT_VERSIONS, SKILL_VERSIONS, build_prompt
from app.v020_repository import V020Repository
from app.v020_run_repository import V020RunRepository
from app.v020_run_schemas import (
    AnalysisModelOutput, CaseModelOutput, ReviewModelOutput, SuggestionModelOutput,
)


class V020RunError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class V020RunService:
    def __init__(
        self,
        projects: ProjectRepository,
        requirements: RequirementRepository,
        workspaces: V020Repository,
        runs: V020RunRepository,
        templates: TemplateMappingRepository,
        real_model_service: ModelService,
    ) -> None:
        self.projects = projects
        self.requirements = requirements
        self.workspaces = workspaces
        self.runs = runs
        self.templates = templates
        self.real_model_service = real_model_service

    def preflight(
        self, project_id: int, page: str, mode: str, session_id: str | None, roles: list[str] | None = None,
        *, template_mode: str = "default", template_mapping_id: int | None = None,
        supplemental_requirements: str = "",
    ) -> dict:
        context = self._input_context(project_id, page, roles or [])
        if page == "cases":
            if not context["selected_rows"]:
                raise V020RunError(409, "尚未勾选测试范围；请先在需求分析表中选择测试点。")
            context["template"] = self._template(project_id, template_mode, template_mapping_id)
            context["supplemental_requirements"] = supplemental_requirements
        input_summary = self._input_summary(context)
        serialized = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        estimated_tokens = max(1, len(serialized) // 4)
        if estimated_tokens > 80_000:
            raise V020RunError(
                422, "当前资料范围超过单次模型上下文能力，请按资料文件或章节缩小范围后再运行。",
            )
        provider = model = credential_source = "不适用"
        verification_status = "本地模式无需验证"
        if mode != "local":
            resolved, status = self._verified_model(session_id)
            provider, model = resolved.provider, resolved.model
            credential_source, verification_status = resolved.credential_source, status.verification_status
        prompt_version = PROMPT_VERSIONS[page].get(mode) if mode != "local" else f"{page}.local.v1"
        return {
            "page": page,
            "mode": mode,
            "provider": provider,
            "model": model,
            "credential_source": credential_source,
            "verification_status": verification_status,
            "input_summary": input_summary,
            "supplemental_notes": context.get("supplemental_notes", ""),
            "supplemental_requirements": context.get("supplemental_requirements", ""),
            "template_filename": context.get("template", {}).get("filename"),
            "prompt_version": prompt_version,
            "skill_version": SKILL_VERSIONS[page] if mode == "skill" else None,
            "estimated_input_tokens": estimated_tokens,
            "max_output_tokens": 10_000 if page == "analysis" else 4_000,
            "estimated_cost": {
                "status": "unavailable", "reason": "当前模型未登记可审计的输入/输出单价，无法估算费用。",
            },
            "requires_confirmation": mode != "local",
        }

    def run(
        self,
        project_id: int,
        page: str,
        mode: str,
        confirmed: bool,
        session_id: str | None,
        *,
        roles: list[str] | None = None,
        template_mode: str = "default",
        template_mapping_id: int | None = None,
        supplemental_requirements: str = "",
    ) -> dict:
        if mode != "local" and not confirmed:
            raise V020RunError(409, "真实模型调用前必须确认输入范围和 Token/费用信息。")
        preflight = self.preflight(
            project_id, page, mode, session_id, roles, template_mode=template_mode,
            template_mapping_id=template_mapping_id, supplemental_requirements=supplemental_requirements,
        )
        context = self._input_context(project_id, page, roles or [])
        if page == "cases":
            context["template"] = self._template(project_id, template_mode, template_mapping_id)
            context["supplemental_requirements"] = supplemental_requirements
        started = datetime.now(UTC)
        started_clock = perf_counter()
        run = self._running_record(project_id, page, mode, preflight, started)
        self.runs.create_run(run)
        try:
            raw, usage = self._produce(page, mode, context, preflight, session_id)
            normalized = self._normalize(page, raw, context, run)
            stage_events = self._completed_events(mode)
            result = self._save_result(
                project_id, page, run, normalized, template_mode, template_mapping_id,
                supplemental_requirements,
            )
            run.update({
                "status": "completed", "stage": "完成", "stage_events": stage_events,
                "duration_ms": max(0, int((perf_counter() - started_clock) * 1000)),
                "completed_at": datetime.now(UTC).isoformat(), "actual_usage": usage,
                "actual_cost": {
                    "status": "unavailable", "reason": "当前模型未登记调用时单价，无法计算实际费用。",
                },
                "error": None,
                "next_step": self._next_step(page),
                "result_summary": self._result_summary(page, normalized),
            })
            self.runs.update_run(run)
            return {"run": run, **result}
        except V020RunError as error:
            run.update({
                "status": "failed", "stage": "失败",
                "stage_events": self._failed_events(mode, str(error)),
                "duration_ms": max(0, int((perf_counter() - started_clock) * 1000)),
                "completed_at": datetime.now(UTC).isoformat(),
                "actual_usage": {"status": "unavailable", "reason": "运行失败，服务商用量不可获得。"},
                "actual_cost": {"status": "unavailable", "reason": "运行失败，费用不可获得。"},
                "error": str(error), "next_step": "根据失败原因修正输入或模型配置后重新运行。",
            })
            self.runs.update_run(run)
            raise
        except Exception as error:
            message = f"运行发生未预期错误：{type(error).__name__}"
            run.update({
                "status": "failed", "stage": "失败",
                "stage_events": self._failed_events(mode, message),
                "duration_ms": max(0, int((perf_counter() - started_clock) * 1000)),
                "completed_at": datetime.now(UTC).isoformat(),
                "actual_usage": {"status": "unavailable", "reason": "运行失败，服务商用量不可获得。"},
                "actual_cost": {"status": "unavailable", "reason": "运行失败，费用不可获得。"},
                "error": message, "next_step": "检查服务日志与模型连接后重新运行。",
            })
            self.runs.update_run(run)
            raise V020RunError(500, message) from error

    def accept_item(self, project_id: int, kind: str, item_id: str, disposition: str) -> dict:
        table = "v020_suggestions" if kind == "suggestion" else "v020_review_suggestions"
        item = self.runs.dispose_item(table, project_id, item_id, disposition)
        if item is None:
            raise V020RunError(404, "建议不存在")
        result = {"item": item, "analysis_row": None}
        if disposition == "accepted":
            row = self._feedback_analysis_row(project_id, kind, item)
            self.runs.save_analysis_rows(project_id, item["run_id"], [row])
            result["analysis_row"] = row
        return result

    def skip_review(self, project_id: int) -> dict:
        if self.projects.get(project_id) is None:
            raise V020RunError(404, "测试设计项目不存在")
        return {"skipped": True, "message": "审核已跳过，可直接进入测试用例。"}

    def edit_case(self, project_id: int, case_id: str, updates: dict) -> dict:
        case = self.runs.update_case(project_id, case_id, updates)
        if case is None:
            raise V020RunError(404, "候选测试用例不存在")
        return case

    def _produce(self, page: str, mode: str, context: dict, preflight: dict, session_id: str | None) -> tuple[dict, dict]:
        if mode == "local":
            output = {
                "analysis": local_analysis, "suggestions": local_suggestions,
                "review": local_review, "cases": local_cases,
            }[page](context)
            return output, {"status": "unavailable", "reason": "本地模式未调用外部模型。"}
        resolved, _ = self._verified_model(session_id)
        prompt = build_prompt(page, mode, context)
        response = self.real_model_service.complete(ModelRequest(
            task_type={
                "analysis": "requirement_review", "suggestions": "scope_analysis",
                "review": "risk_analysis", "cases": "case_generation",
            }[page],
            prompt_version=preflight["prompt_version"],
            model_parameters=AIModelConfig(
                provider=resolved.provider, model=resolved.model, temperature=0,
                max_tokens=preflight["max_output_tokens"],
            ),
            input_asset_versions=(), scenario="normal", base_url=resolved.base_url,
            api_key=resolved.api_key, prompt_override=prompt,
        ))
        if response.error_code or not isinstance(response.raw_output, dict):
            raise V020RunError(502, f"模型调用失败：{response.error_code or '返回内容不是 JSON 对象'}")
        if response.total_tokens is None and response.input_tokens is None and response.output_tokens is None:
            usage = {"status": "unavailable", "reason": "服务商未返回 Token 用量。"}
        else:
            usage = {
                "status": "available", "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens, "total_tokens": response.total_tokens,
            }
        return response.raw_output, usage

    def _normalize(self, page: str, raw: dict, context: dict, run: dict) -> list[dict]:
        model = {
            "analysis": AnalysisModelOutput,
            "suggestions": SuggestionModelOutput,
            "review": ReviewModelOutput,
            "cases": CaseModelOutput,
        }[page]
        try:
            parsed = model.model_validate(raw)
        except ValueError as error:
            raise V020RunError(422, f"模型输出结构校验失败：{str(error)[:400]}") from error
        key = "rows" if page == "analysis" else "candidates" if page == "cases" else "suggestions"
        items = [item.model_dump(mode="json") for item in getattr(parsed, key)]
        if page == "analysis":
            source_by_id = {
                f"input-{index}": fragment["source_reference"]
                for index, fragment in enumerate(context["fragments"], start=1)
            }
            normalized = []
            for item in items:
                source = source_by_id.get(item["source_reference_id"])
                if source is None:
                    raise V020RunError(422, "模型输出引用了输入范围外的来源。")
                normalized.append({
                    "id": f"analysis-{uuid4().hex}", "project_id": run["project_id"], "run_id": run["id"],
                    **item, "source": f"{source['filename']} · {source['locator']}",
                    "source_reference": source, "selected": False, "origin": "analysis", "mode": run["mode"],
                })
            return normalized
        if page == "cases":
            allowed = {row["id"] for row in context["selected_rows"]}
            if any(item["analysis_row_id"] not in allowed for item in items):
                raise V020RunError(422, "模型输出包含未勾选或无法追溯的测试点。")
            row_by_id = {row["id"]: row for row in context["selected_rows"]}
            for item in items:
                source = row_by_id[item["analysis_row_id"]]
                item.update({"module": source["module"], "test_item": source["test_item"],
                             "test_point": source["test_point"], "source": source["source"]})
        if page in {"suggestions", "review"}:
            allowed_rows = {row["id"] for row in context["analysis_rows"]}
            if any(item.get("related_analysis_row_id") not in allowed_rows | {None} for item in items):
                raise V020RunError(422, "模型输出引用了输入范围外的需求分析结果。")
        if page == "review":
            allowed_roles = set(context["roles"])
            if any(item["role"] not in allowed_roles for item in items):
                raise V020RunError(422, "模型输出包含未选择的审核身份。")
        return [{
            "id": f"{page}-{uuid4().hex}", "project_id": run["project_id"], "run_id": run["id"],
            **item, **({"disposition": "pending"} if page in {"suggestions", "review"}
                       else {"included": True, "removed": False, "mode": run["mode"]}),
        } for item in items]

    def _save_result(
        self, project_id: int, page: str, run: dict, items: list[dict], template_mode: str,
        template_mapping_id: int | None, supplemental_requirements: str,
    ) -> dict:
        if page == "analysis":
            return {"rows": self.runs.save_analysis_rows(project_id, run["id"], items)}
        if page == "suggestions":
            return {"suggestions": self.runs.save_items("v020_suggestions", project_id, run["id"], items)}
        if page == "review":
            return {"suggestions": self.runs.save_items("v020_review_suggestions", project_id, run["id"], items)}
        template = self._template(project_id, template_mode, template_mapping_id)
        generation = {
            "id": f"generation-{uuid4().hex}", "project_id": project_id, "run_id": run["id"],
            "scope_ids": [item["analysis_row_id"] for item in items], "template": template,
            "supplemental_requirements": supplemental_requirements,
        }
        for item in items:
            item["generation_id"] = generation["id"]
        self.runs.create_generation(generation, items)
        self.workspaces.save_template(
            project_id, template_mode, template_mapping_id if template_mode == "uploaded" else None,
        )
        return {"generation_id": generation["id"], "scope_ids": generation["scope_ids"],
                "template": template, "cases": items}

    def _input_context(self, project_id: int, page: str, roles: list[str]) -> dict:
        project = self.projects.get(project_id)
        if project is None:
            raise V020RunError(404, "测试设计项目不存在")
        state = self.workspaces.workspace_row(project_id)
        version = self.requirements.get_version(project_id, state["active_requirement_version_id"])
        if version is None:
            raise V020RunError(409, "请先在上传文档页上传并解析至少一份可用资料。")
        base = {
            "test_object": project.test_object, "software_version": project.software_version,
            "requirement_version_id": version.id, "supplemental_notes": state["supplemental_notes"],
        }
        if page == "analysis":
            base["fragments"] = [fragment.model_dump(mode="json") for material in version.materials
                                 for fragment in material.fragments]
            if not base["fragments"]:
                raise V020RunError(409, "当前资料没有可用于需求分析的文本片段。")
        else:
            rows = self.runs.analysis_rows(project_id)
            if not rows:
                raise V020RunError(409, "请先完成需求分析。")
            base["analysis_rows"] = rows
            base["selected_rows"] = [row for row in rows if row["selected"]]
            if page == "review":
                base["roles"] = roles
        return base

    @staticmethod
    def _input_summary(context: dict) -> dict:
        fragments = context.get("fragments", [])
        rows = context.get("analysis_rows", [])
        filenames = {item["source_reference"]["filename"] for item in fragments}
        return {
            "file_count": len(filenames), "fragment_count": len(fragments),
            "analysis_row_count": len(rows), "selected_row_count": len(context.get("selected_rows", [])),
            "requirement_version_id": context["requirement_version_id"],
            "roles": context.get("roles", []),
        }

    @staticmethod
    def _running_record(project_id: int, page: str, mode: str, preflight: dict, started: datetime) -> dict:
        return {
            "id": f"run-{uuid4().hex}", "project_id": project_id, "page": page, "mode": mode,
            "status": "running", "source_label": {
                "direct": "真实模型（直接调用）", "skill": "真实模型（Skill 工作流）",
                "local": "本地模拟（未调用 AI）",
            }[mode],
            "provider": preflight["provider"], "model": preflight["model"],
            "credential_source": preflight["credential_source"],
            "input_summary": preflight["input_summary"], "prompt_version": preflight["prompt_version"],
            "skill_version": preflight["skill_version"],
            "estimated_input_tokens": preflight["estimated_input_tokens"],
            "max_output_tokens": preflight["max_output_tokens"], "estimated_cost": preflight["estimated_cost"],
            "stage": "准备输入", "stage_events": [], "duration_ms": None,
            "started_at": started.isoformat(), "completed_at": None, "actual_usage": None,
            "actual_cost": None, "error": None, "next_step": "等待运行完成。", "result_summary": None,
        }

    @staticmethod
    def _completed_events(mode: str) -> list[dict]:
        detail = "本地模式跳过外部模型调用，生成确定性结果。" if mode == "local" else "模型调用完成。"
        return [{"stage": stage, "status": "completed", "detail": detail if stage == "调用模型" else "已完成"}
                for stage in ("准备输入", "调用模型", "校验输出", "保存结果", "完成")]

    @staticmethod
    def _failed_events(mode: str, message: str) -> list[dict]:
        return [
            {"stage": "准备输入", "status": "completed", "detail": "已完成"},
            {"stage": "调用模型", "status": "failed", "detail": message if mode != "local" else "本地生成失败"},
            {"stage": "失败", "status": "failed", "detail": message},
        ]

    @staticmethod
    def _result_summary(page: str, items: list[dict]) -> dict:
        return {"count": len(items), "label": {
            "analysis": "需求分析项", "suggestions": "新增建议", "review": "审核建议", "cases": "候选用例",
        }[page]}

    @staticmethod
    def _next_step(page: str) -> str:
        return {
            "analysis": "筛选并勾选将用于生成测试用例的范围。",
            "suggestions": "逐条接纳或拒绝建议；接纳项会回流需求分析表且默认不勾选。",
            "review": "逐条决定是否接纳，或直接进入测试用例。",
            "cases": "预览、编辑并选择纳入的候选用例，然后导出。",
        }[page]

    def _verified_model(self, session_id: str | None):
        resolved = get_session_model_config(session_id)
        status = get_session_model_status(session_id)
        if resolved is None or status is None or status.verification_status != "verified":
            raise V020RunError(409, "当前真实模型连接尚未验证；请打开已有模型配置并完成连接测试。")
        return resolved, status

    def _template(self, project_id: int, mode: str, mapping_id: int | None) -> dict:
        if mode == "default":
            mapping, _ = default_template(project_id)
            return mapping.model_dump(mode="json")
        if mapping_id is None:
            raise V020RunError(422, "选择上传模板时必须先上传并确认模板字段映射。")
        mapping = self.templates.get(project_id, mapping_id)
        if mapping is None or mapping.status != "confirmed":
            raise V020RunError(409, "上传模板尚未完成字段解析与映射确认。")
        return mapping.model_dump(mode="json")

    @staticmethod
    def _feedback_analysis_row(project_id: int, kind: str, item: dict) -> dict:
        content = item["content"]
        return {
            "id": f"analysis-{uuid4().hex}", "project_id": project_id, "run_id": item["run_id"],
            "module": "AI 建议", "function_point": content[:40], "test_item": content[:60],
            "test_point": content, "source_reference_id": item["id"],
            "source": "新增建议" if kind == "suggestion" else "AI 角色审核",
            "source_reference": {"reference_id": item["id"], "filename": "AI 建议", "locator": kind},
            "ai_reason": item["ai_reason"], "information_gap": "", "status": "ready",
            "selected": False, "origin": kind, "mode": "derived",
        }
