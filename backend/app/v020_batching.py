import json

from app.ai_schemas import AIModelConfig
from app.ai_service import ModelRequest
from app.v020_model_errors import V020RunError, model_failure
from app.v020_prompts import build_prompt
from app.v020_run_schemas import (
    AnalysisModelOutput, CaseModelOutput, MaterialUnderstandingOutput, ReviewModelOutput, SuggestionModelOutput,
)


MAX_FRAGMENTS_PER_REQUEST = 2
PER_REQUEST_OUTPUT_TOKENS = 3_000


def batch_contexts(page: str, context: dict) -> list[dict]:
    """资料理解和需求分析按来源块拆分；其余阶段保持一次调用。"""
    if page not in {"understanding", "analysis"}:
        return [context]
    fragments = context.get("fragments", [])
    batches = []
    for start in range(0, len(fragments), MAX_FRAGMENTS_PER_REQUEST):
        batch = {**context, "fragments": fragments[start:start + MAX_FRAGMENTS_PER_REQUEST]}
        batch["request_scope"] = {
            "completed_before": start,
            "source_ids": [item["source_reference_id"] for item in batch["fragments"]],
        }
        batches.append(batch)
    return batches


def merge_batch_outputs(page: str, outputs: list[dict]) -> dict:
    if len(outputs) == 1:
        return outputs[0]
    if page == "understanding":
        return {
            "overview": "\n".join(
                value for output in outputs if (value := str(output.get("overview", "")).strip())
            ),
            "organized_fragments": [
                item for output in outputs for item in output.get("organized_fragments", [])
            ],
        }
    if page == "analysis":
        rows: list[dict] = []
        seen: set[str] = set()
        for output in outputs:
            for row in output.get("rows", []):
                key = json.dumps({
                    "module": _normal(row.get("module")),
                    "test_item": _normal(row.get("test_item")),
                    "test_type": _normal(row.get("test_type")),
                    "source_reference_id": row.get("source_reference_id"),
                }, ensure_ascii=False, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
        return {"rows": rows}
    return outputs[0]


def aggregate_usage(usages: list[dict]) -> dict:
    available = [usage for usage in usages if usage.get("status") == "available"]
    if len(available) != len(usages):
        return {"status": "unavailable", "reason": "部分或全部来源范围未返回 Token 用量，不能可靠汇总。"}
    return {
        "status": "available",
        "input_tokens": _sum_optional(available, "input_tokens"),
        "output_tokens": _sum_optional(available, "output_tokens"),
        "total_tokens": _sum_optional(available, "total_tokens"),
    }


def execute_model_batches(
    model_service, run_repository, resolved, page: str, mode: str, context: dict, preflight: dict, run: dict,
) -> tuple[dict, dict]:
    contexts = batch_contexts(page, context)
    outputs = [checkpoint["output"] for checkpoint in run.get("checkpoints", [])]
    usages = [checkpoint["usage"] for checkpoint in run.get("checkpoints", [])]
    for index, batch_context in enumerate(contexts[len(outputs):], start=len(outputs) + 1):
        if _cancel_requested(run_repository, run):
            raise V020RunError(409, "本次运行已停止；已完成的来源范围已保留，可稍后继续。")
        response = None
        for attempt in range(1, 3):
            if _cancel_requested(run_repository, run):
                raise V020RunError(409, "本次运行已停止；已完成的来源范围已保留，可稍后继续。")
            response = model_service.complete(ModelRequest(
                task_type={
                    "understanding": "requirement_review", "analysis": "requirement_review",
                    "suggestions": "scope_analysis", "review": "risk_analysis", "cases": "case_generation",
                }[page],
                prompt_version=preflight["prompt_version"],
                model_parameters=AIModelConfig(
                    provider=resolved.provider, model=resolved.model, temperature=0,
                    max_tokens=preflight["max_output_tokens"],
                ),
                input_asset_versions=(), scenario="normal", base_url=resolved.base_url,
                api_key=resolved.api_key, prompt_override=build_prompt(page, mode, batch_context),
                network_mode=resolved.network_mode,
                cancel_requested=lambda: _cancel_requested(run_repository, run),
            ))
            run["attempts"].append({
                "unit": index, "attempt": attempt, "error_code": response.error_code,
                "duration_ms": response.duration_ms, "first_event_ms": response.first_event_ms,
            })
            run_repository.update_run(run)
            if run.get("cancel_requested") and response.error_code != "provider_cancelled":
                raise V020RunError(409, "本次运行已停止；已完成的来源范围已保留，可稍后继续。")
            if not response.error_code or not response.retryable or attempt == 2:
                break
        assert response is not None
        if response.error_code == "provider_cancelled":
            raise V020RunError(409, "本次运行已停止；已完成的来源范围已保留，可稍后继续。")
        if response.error_code:
            status_code, detail = model_failure(response, preflight["provider"], preflight["model"], page)
            raise V020RunError(status_code, detail)
        if not isinstance(response.raw_output, dict):
            raise V020RunError(502, "模型调用失败：返回内容不是 JSON 对象")
        validate_batch_output(page, response.raw_output, batch_context)
        usage = response_usage(response)
        outputs.append(response.raw_output)
        usages.append(usage)
        run["checkpoints"].append({"unit": index, "output": response.raw_output, "usage": usage})
        run["progress"] = {"completed_units": index, "total_units": len(contexts), "stage": "调用模型"}
        run["stage"] = f"已处理 {index}/{len(contexts)} 个来源范围"
        run_repository.update_run(run)
    run["progress"]["stage"] = "保存结果"
    return merge_batch_outputs(page, outputs), aggregate_usage(usages)


def response_usage(response) -> dict:
    if response.total_tokens is None and response.input_tokens is None and response.output_tokens is None:
        return {"status": "unavailable", "reason": "服务商未返回 Token 用量。"}
    return {
        "status": "available", "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens, "total_tokens": response.total_tokens,
    }


def _cancel_requested(run_repository, run: dict) -> bool:
    cancelled = bool((run_repository.get_run(run["project_id"], run["id"]) or {}).get("cancel_requested"))
    if cancelled:
        run["cancel_requested"] = True
    return cancelled


def validate_batch_output(page: str, raw: dict, context: dict) -> None:
    model = {
        "understanding": MaterialUnderstandingOutput,
        "analysis": AnalysisModelOutput,
        "suggestions": SuggestionModelOutput,
        "review": ReviewModelOutput,
        "cases": CaseModelOutput,
    }[page]
    try:
        parsed = model.model_validate(raw)
    except ValueError as error:
        raise V020RunError(422, f"模型输出结构校验失败：{str(error)[:400]}") from error
    if page == "understanding":
        expected = {item["source_reference_id"] for item in context["fragments"]}
        received = [item.source_reference_id for item in parsed.organized_fragments]
        if len(received) != len(set(received)) or set(received) != expected:
            raise V020RunError(422, "资料理解结果必须逐一覆盖本次输入来源块，且不能重复或越界。")
    elif page == "analysis":
        allowed = {item["source_reference_id"] for item in context["fragments"]}
        if any(item.source_reference_id not in allowed for item in parsed.rows):
            raise V020RunError(422, "模型输出引用了本次输入范围外的来源。")
    elif page == "cases":
        allowed = {item["id"] for item in context["selected_rows"]}
        if any(item.analysis_row_id not in allowed for item in parsed.candidates):
            raise V020RunError(422, "模型输出包含未勾选或无法追溯的测试点。")
    elif page in {"suggestions", "review"}:
        rows = {item["id"]: item for item in context["analysis_rows"]}
        suggestions = parsed.suggestions
        for item in suggestions:
            row_id = item.related_analysis_row_id
            if row_id is not None and row_id not in rows:
                raise V020RunError(422, "模型输出引用了输入范围外的需求分析结果。")
            if row_id is not None and item.related_requirement_id != rows[row_id]["related_requirement_id"]:
                raise V020RunError(422, "模型输出的关联需求 ID 与引用的需求分析结果不一致。")
        if page == "review" and any(item.role not in set(context["roles"]) for item in suggestions):
            raise V020RunError(422, "模型输出包含未选择的审核身份。")


def _sum_optional(values: list[dict], key: str) -> int | None:
    present = [value[key] for value in values if isinstance(value.get(key), int)]
    return sum(present) if present else None


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())
