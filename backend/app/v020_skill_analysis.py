import json
from math import ceil
from copy import deepcopy

from app.ai_schemas import AIModelConfig
from app.ai_service import ModelRequest
from app.v020_batching import aggregate_usage, response_usage
from app.v020_contracts import TEST_TYPES
from app.v020_model_errors import V020RunError, model_failure
from app.v020_skill_batching import (
    SkillStageBatch, canonicalize_batch_output, merge_stage_outputs, split_batch, stage_batches,
)
from app.v020_skill_contracts import (
    MODEL_STAGES, SKILL_PROMPT_VERSION, SKILL_STAGE_COUNT, SKILL_STAGE_OUTPUT_TOKENS,
    StageDefinition, build_stage_prompt,
)


class StageOutputInvalid(Exception):
    def __init__(self, stage_id: str, errors: list[dict]) -> None:
        self.stage_id = stage_id
        self.errors = errors
        super().__init__(_validation_message(stage_id, errors, repaired=False))


def execute_skill_analysis(model_service, run_repository, resolved, context: dict, preflight: dict, run: dict):
    stage_checkpoints = {
        item.get("stage_id"): item for item in run.get("checkpoints", [])
        if item.get("stage_id") and item.get("checkpoint_type") != "skill_batch"
    }
    artifacts = {stage_id: item["output"] for stage_id, item in stage_checkpoints.items() if "output" in item}
    usages = [
        item["usage"] for item in run.get("checkpoints", [])
        if item.get("usage") and (
            item.get("checkpoint_type") == "skill_batch"
            or item.get("checkpoint_type") is None and item.get("model_call")
        )
    ]
    for position, stage in enumerate(MODEL_STAGES, start=1):
        if stage.stage_id in artifacts:
            continue
        _ensure_not_cancelled(run_repository, run)
        saved_batches = [
            item for item in run.get("checkpoints", [])
            if item.get("checkpoint_type") == "skill_batch" and item.get("stage_id") == stage.stage_id
        ]
        completed_scope_ids = {
            scope_id for item in saved_batches for scope_id in item.get("scope_ids", [])
        }
        queue = stage_batches(stage, context, artifacts, completed_scope_ids)
        batch_outputs = [item["output"] for item in saved_batches]
        while queue:
            _ensure_not_cancelled(run_repository, run)
            batch = queue.pop(0)
            batch_number = len(saved_batches) + 1
            batch_count = len(saved_batches) + len(queue) + 1
            _set_batch_progress(run_repository, run, position - 1, stage, batch_number, batch_count)
            prompt = build_stage_prompt(stage, batch.context, batch.artifacts, _batch_scope(batch, batch_number, batch_count))
            if _estimate_tokens(prompt) + SKILL_STAGE_OUTPUT_TOKENS > 32_000:
                if len(batch.scope_ids) > 1:
                    queue[0:0] = split_batch(stage, context, artifacts, batch)
                    continue
                raise V020RunError(
                    422, f"{stage.stage_id} 的单个语义范围与预留输出仍超过 32k 保守上下文上限；"
                    "请缩小对应资料范围后重试。",
                )
            response = _call_stage_model(
                model_service, run_repository, resolved, run, stage, position, batch, prompt,
            )
            if response.error_code == "provider_response_truncated" and len(batch.scope_ids) > 1:
                queue[0:0] = split_batch(stage, context, artifacts, batch)
                continue
            if response.error_code:
                _raise_model_error(response, preflight)
            if not isinstance(response.raw_output, dict):
                raise V020RunError(502, f"{stage.stage_id} 模型返回内容不是 JSON 对象。")
            candidate = canonicalize_batch_output(
                stage, _safe_stage_defaults(stage, response.raw_output), batch,
            )
            usage = response_usage(response)
            output, usage, repair_applied = _validate_or_repair_batch(
                model_service, run_repository, resolved, run, stage, position, batch, candidate, usage, preflight,
            )
            usages.append(usage)
            checkpoint = {
                "checkpoint_type": "skill_batch", "unit": position, "stage_id": stage.stage_id,
                "stage_name": stage.name, "batch_index": batch_number, "scope_ids": list(batch.scope_ids),
                "model_call": True, "repair_applied": repair_applied, "output": output, "usage": usage,
            }
            run["checkpoints"].append(checkpoint)
            saved_batches.append(checkpoint)
            batch_outputs.append(output)
            run_repository.update_run(run)
        output = merge_stage_outputs(stage, batch_outputs)
        output = _validate_stage(stage, output, context, artifacts)
        if stage.stage_id == "S00" and not output["atomic_requirements"]:
            raise V020RunError(422, "S00 未从当前资料中识别出可用于测试设计的原子需求。")
        artifacts[stage.stage_id] = output
        run["checkpoints"].append({
            "checkpoint_type": "skill_stage", "unit": position, "stage_id": stage.stage_id,
            "stage_name": stage.name, "model_call": False, "output": output,
        })
        _set_progress(run_repository, run, position, stage, "阶段完成")

    if "S07" not in artifacts:
        rows = _merge_rows(*(artifacts[stage_id]["rows"] for stage_id in ("S03", "S04", "S05", "S06")))
        artifacts["S07"] = {"rows": rows}
        run["checkpoints"].append({"unit": 8, "stage_id": "S07", "stage_name": "测试项汇总", "model_call": False,
                                   "output": artifacts["S07"]})
        _set_local_progress(run_repository, run, 8, "S07 测试项汇总")
    if "S08" not in artifacts:
        coverage = _coverage(artifacts["S00"], artifacts["S07"])
        if coverage["uncovered_requirement_ids"]:
            missing = "、".join(coverage["uncovered_requirement_ids"][:20])
            raise V020RunError(422, f"S08 覆盖校验未通过，以下原子需求尚无测试项：{missing}")
        artifacts["S08"] = coverage
        run["checkpoints"].append({"unit": 9, "stage_id": "S08", "stage_name": "覆盖校验", "model_call": False,
                                   "output": coverage})
        _set_local_progress(run_repository, run, 9, "S08 覆盖校验")
    return artifacts["S07"], aggregate_usage(usages)


def _batch_scope(batch: SkillStageBatch, batch_number: int, batch_count: int) -> dict:
    source_ids = [item["source_reference_id"] for item in batch.context["fragments"]]
    requirement_ids = [
        item["requirement_id"]
        for item in batch.artifacts.get("S00", {}).get("atomic_requirements", [])
    ]
    return {
        "batch_number": batch_number,
        "batch_count": batch_count,
        "source_reference_ids": source_ids,
        "requirement_ids": requirement_ids,
    }


def _call_stage_model(model_service, repository, resolved, run: dict, stage: StageDefinition, position: int,
                      batch: SkillStageBatch, prompt: str):
    response = None
    for attempt in range(1, 3):
        _ensure_not_cancelled(repository, run)
        response = model_service.complete(ModelRequest(
            task_type="requirement_review",
            prompt_version=f"{SKILL_PROMPT_VERSION}.{stage.stage_id.lower()}",
            model_parameters=AIModelConfig(
                provider=resolved.provider, model=resolved.model, temperature=0,
                max_tokens=SKILL_STAGE_OUTPUT_TOKENS,
            ),
            input_asset_versions=(), scenario="normal", base_url=resolved.base_url, api_key=resolved.api_key,
            prompt_override=prompt, network_mode=resolved.network_mode,
            cancel_requested=lambda: _is_cancelled(repository, run),
        ))
        _record_attempt(repository, run, response, position, stage.stage_id, attempt, batch)
        if not response.error_code or not response.retryable or attempt == 2:
            break
    assert response is not None
    return response


def _validate_or_repair_batch(
    model_service, repository, resolved, run: dict, stage: StageDefinition, position: int,
    batch: SkillStageBatch, candidate: dict, usage: dict, preflight: dict,
) -> tuple[dict, dict, bool]:
    try:
        return _validate_stage(stage, candidate, batch.context, batch.artifacts), usage, False
    except StageOutputInvalid as validation_error:
        repair_prompt = _repair_prompt(
            stage, candidate, validation_error.errors, batch.context, batch.artifacts,
        )
        if _estimate_tokens(repair_prompt) + SKILL_STAGE_OUTPUT_TOKENS > 32_000:
            reason = _validation_message(stage.stage_id, validation_error.errors, repaired=False)
            raise V020RunError(422, f"{reason} 自动修复请求超过 32k 保守上下文上限。")
        repair_response = model_service.complete(ModelRequest(
            task_type="requirement_review",
            prompt_version=f"{SKILL_PROMPT_VERSION}.{stage.stage_id.lower()}.repair",
            model_parameters=AIModelConfig(
                provider=resolved.provider, model=resolved.model, temperature=0,
                max_tokens=SKILL_STAGE_OUTPUT_TOKENS,
            ),
            input_asset_versions=(), scenario="normal", base_url=resolved.base_url, api_key=resolved.api_key,
            prompt_override=repair_prompt, network_mode=resolved.network_mode,
            cancel_requested=lambda: _is_cancelled(repository, run),
        ))
        _record_attempt(
            repository, run, repair_response, position, stage.stage_id, 1, batch,
            operation="schema_repair",
        )
        if repair_response.error_code:
            _raise_model_error(repair_response, preflight)
        if not isinstance(repair_response.raw_output, dict):
            raise V020RunError(502, f"{stage.stage_id} 结构修复返回内容不是 JSON 对象。")
        repaired = canonicalize_batch_output(
            stage, _safe_stage_defaults(stage, repair_response.raw_output), batch,
        )
        _ensure_repair_preserves_rows(stage, candidate, repaired)
        try:
            output = _validate_stage(stage, repaired, batch.context, batch.artifacts)
        except StageOutputInvalid as repair_error:
            raise V020RunError(422, _validation_message(stage.stage_id, repair_error.errors, repaired=True))
        return output, aggregate_usage([usage, response_usage(repair_response)]), True


def _record_attempt(repository, run: dict, response, position: int, stage_id: str, attempt: int,
                    batch: SkillStageBatch, operation: str = "generate") -> None:
    run["attempts"].append({
        "unit": position, "stage_id": stage_id, "batch_scope_ids": list(batch.scope_ids),
        "attempt": attempt, "operation": operation, "error_code": response.error_code,
        "duration_ms": response.duration_ms, "first_event_ms": response.first_event_ms,
        "finish_reason": response.finish_reason, "response_length": response.response_length,
        "diagnostic": response.diagnostic,
    })
    repository.update_run(run)


def _raise_model_error(response, preflight: dict) -> None:
    if response.error_code == "provider_cancelled":
        raise V020RunError(409, "本次运行已停止；已完成批次和阶段已保留，可稍后继续。")
    status, detail = model_failure(response, preflight["provider"], preflight["model"], "analysis")
    raise V020RunError(status, detail)


def _validate_stage(stage: StageDefinition, raw: dict, context: dict, artifacts: dict[str, dict]) -> dict:
    try:
        parsed = stage.model.model_validate(raw)
    except ValueError as error:
        raise StageOutputInvalid(stage.stage_id, error.errors()) from error
    output = parsed.model_dump(mode="json")
    sources = {item["source_reference_id"] for item in context["fragments"]}
    if stage.stage_id == "S00":
        if any(item["source_reference_id"] not in sources for item in output["atomic_requirements"]):
            raise V020RunError(422, "S00 输出引用了资料范围外的来源。")
        ids = [item["requirement_id"] for item in output["atomic_requirements"]]
        if len(ids) != len(set(ids)):
            raise V020RunError(422, "S00 原子需求 ID 必须唯一。")
        coverage_ids = [item["source_reference_id"] for item in output["source_coverage"]]
        if len(coverage_ids) != len(set(coverage_ids)) or set(coverage_ids) != sources:
            raise StageOutputInvalid("S00", [{"loc": ("source_coverage",), "type": "coverage_mismatch"}])
        atomic_by_source: dict[str, set[str]] = {source_id: set() for source_id in sources}
        for item in output["atomic_requirements"]:
            atomic_by_source[item["source_reference_id"]].add(item["requirement_id"])
        if any(set(item["requirement_ids"]) != atomic_by_source[item["source_reference_id"]]
               for item in output["source_coverage"]):
            raise StageOutputInvalid("S00", [{"loc": ("source_coverage",), "type": "requirement_link_mismatch"}])
    requirement_ids = {item["requirement_id"] for item in artifacts.get("S00", {}).get("atomic_requirements", [])}
    if stage.stage_id in {"S01", "S02"}:
        key = "functions" if stage.stage_id == "S01" else "rules"
        if any(set(item["requirement_ids"]) - requirement_ids for item in output[key]):
            raise V020RunError(422, f"{stage.stage_id} 输出引用了不存在的原子需求 ID。")
    if stage.stage_id in {"S03", "S04", "S05", "S06"}:
        if any(item["source_reference_id"] not in sources for item in output["rows"]):
            raise V020RunError(422, f"{stage.stage_id} 输出引用了资料范围外的来源。")
        if any(item["related_requirement_id"] not in requirement_ids for item in output["rows"]):
            raise V020RunError(422, f"{stage.stage_id} 输出引用了不存在的原子需求 ID。")
    return output


def _safe_stage_defaults(stage: StageDefinition, raw: dict) -> dict:
    candidate = deepcopy(raw)
    if stage.stage_id == "S04" and isinstance(candidate.get("rows"), list):
        for row in candidate["rows"]:
            if isinstance(row, dict):
                row.setdefault("test_type", "异常测试")
    return candidate


def _repair_prompt(
    stage: StageDefinition, invalid_output: dict, errors: list[dict], context: dict, artifacts: dict[str, dict],
) -> str:
    compact_errors = [{"path": ".".join(map(str, item.get("loc", ()))), "type": item.get("type", "invalid")}
                      for item in errors[:100]]
    repair_context: dict[str, object] = {
        "allowed_source_reference_ids": [item["source_reference_id"] for item in context["fragments"]],
        "allowed_requirement_ids": [
            item["requirement_id"] for item in artifacts.get("S00", {}).get("atomic_requirements", [])
        ],
        "validation_errors": compact_errors,
        "invalid_output": invalid_output,
    }
    if stage.stage_id == "S00":
        covered = {item.get("source_reference_id") for item in invalid_output.get("source_coverage", [])
                   if isinstance(item, dict)}
        repair_context["materials_missing_coverage"] = [
            item for item in context["fragments"] if item["source_reference_id"] not in covered
        ]
        return (
            f"提示版本：{SKILL_PROMPT_VERSION}.s00.repair。\n当前阶段：S00 结构修复。"
            "修复 atomic_requirements、source_coverage 和 questions。source_coverage 必须逐一覆盖"
            " allowed_source_reference_ids，不能重复或遗漏。有需求的来源列出全部 requirement_ids；"
            "没有需求的来源必须填写 no_requirement_reason。只可依据 materials_missing_coverage 补充遗漏内容，"
            "不得删除已有原子需求。只输出完整 JSON 对象，不要解释。\n"
            + json.dumps(repair_context, ensure_ascii=False, separators=(",", ":"))
        )
    if stage.stage_id in {"S01", "S02"}:
        return (
            f"提示版本：{SKILL_PROMPT_VERSION}.{stage.stage_id.lower()}.repair。\n"
            f"当前阶段：{stage.stage_id} 结构修复。只修复缺失字段和 JSON 结构，"
            "不得删除或改写已有的有效业务内容和 ID。"
            f"输出契约：{stage.output_contract}。只输出完整 JSON 对象，不要解释。\n"
            + json.dumps(repair_context, ensure_ascii=False, separators=(",", ":"))
        )
    return (
        f"提示版本：{SKILL_PROMPT_VERSION}.{stage.stage_id.lower()}.repair。\n"
        f"当前阶段：{stage.stage_id} 结构修复。只修复下面 JSON 的结构和缺失字段。"
        "不得增加、删除或改写测试项，不得改变 module、test_item、test_basis、source_reference_id、"
        "related_requirement_id；每行必须包含 test_type 和 priority。"
        f"test_type 只能从以下分类中选择：{'、'.join(TEST_TYPES)}；priority 只能是 P0、P1、P2、P3。"
        "只输出修复后的 JSON 对象，不要解释。\n"
        + json.dumps(repair_context, ensure_ascii=False, separators=(",", ":"))
    )


def _ensure_repair_preserves_rows(stage: StageDefinition, before: dict, after: dict) -> None:
    if stage.stage_id not in {"S03", "S04", "S05", "S06"}:
        return
    before_rows, after_rows = before.get("rows"), after.get("rows")
    if not isinstance(before_rows, list) or not isinstance(after_rows, list) or len(before_rows) != len(after_rows):
        raise V020RunError(422, f"{stage.stage_id} 结构修复改变了测试项数量，已拒绝该结果。")
    protected = ("module", "test_item", "test_basis", "source_reference_id", "related_requirement_id")
    if any(any(original.get(key) != repaired.get(key) for key in protected)
           for original, repaired in zip(before_rows, after_rows)):
        raise V020RunError(422, f"{stage.stage_id} 结构修复改写了测试项内容，已拒绝该结果。")
    valid_values = {"test_type": set(TEST_TYPES), "priority": {"P0", "P1", "P2", "P3"}}
    if any(any(original.get(key) in allowed and original.get(key) != repaired.get(key)
               for key, allowed in valid_values.items())
           for original, repaired in zip(before_rows, after_rows)):
        raise V020RunError(422, f"{stage.stage_id} 结构修复改写了已有的有效分类，已拒绝该结果。")


def _validation_message(stage_id: str, errors: list[dict], *, repaired: bool) -> str:
    missing: dict[str, int] = {}
    invalid: dict[str, int] = {}
    invalid_count = 0
    for item in errors:
        if item.get("type") == "missing" and item.get("loc"):
            field = str(item["loc"][-1])
            missing[field] = missing.get(field, 0) + 1
        else:
            invalid_count += 1
            field = str(item.get("loc", ("结构",))[-1])
            invalid[field] = invalid.get(field, 0) + 1
    details = []
    if missing:
        details.append("缺少字段 " + "、".join(f"{field}（{count} 处）" for field, count in sorted(missing.items())))
    if invalid_count:
        details.append("字段或结构不合法 " + "、".join(
            f"{field}（{count} 处）" for field, count in sorted(invalid.items())
        ))
    phase = "一次结构修复后仍" if repaired else ""
    return f"{stage_id} 模型输出{phase}不符合字段契约：{'；'.join(details) or '结构不合法'}。"


def _merge_rows(*groups: list[dict]) -> list[dict]:
    rows, seen = [], set()
    for group in groups:
        for row in group:
            key = tuple(" ".join(str(row[field]).lower().split()) for field in
                        ("module", "test_item", "test_type", "related_requirement_id"))
            if key not in seen:
                seen.add(key)
                rows.append(row)
    if not rows:
        raise V020RunError(422, "S07 未得到任何可用测试项。")
    return rows


def _coverage(stage00: dict, stage07: dict) -> dict:
    expected = {item["requirement_id"] for item in stage00["atomic_requirements"]}
    covered = {item["related_requirement_id"] for item in stage07["rows"]}
    return {"covered_requirement_ids": sorted(expected & covered),
            "uncovered_requirement_ids": sorted(expected - covered), "passed": expected <= covered}


def _set_progress(repository, run: dict, completed: int, stage: StageDefinition, status: str) -> None:
    run["stage"] = f"{stage.stage_id} {stage.name} · {status}"
    run["progress"] = {"completed_units": completed, "total_units": SKILL_STAGE_COUNT, "stage": run["stage"]}
    repository.update_run(run)


def _set_batch_progress(repository, run: dict, completed: int, stage: StageDefinition,
                        batch_number: int, batch_count: int) -> None:
    run["stage"] = f"{stage.stage_id} {stage.name} · 模型批次 {batch_number}/{batch_count}"
    run["progress"] = {
        "completed_units": completed, "total_units": SKILL_STAGE_COUNT, "stage": run["stage"],
        "current_batch": batch_number, "stage_batch_count": batch_count,
    }
    repository.update_run(run)


def _set_local_progress(repository, run: dict, completed: int, label: str) -> None:
    run["stage"] = label
    run["progress"] = {"completed_units": completed, "total_units": SKILL_STAGE_COUNT, "stage": label}
    repository.update_run(run)


def _is_cancelled(repository, run: dict) -> bool:
    cancelled = bool((repository.get_run(run["project_id"], run["id"]) or {}).get("cancel_requested"))
    if cancelled:
        run["cancel_requested"] = True
    return cancelled


def _ensure_not_cancelled(repository, run: dict) -> None:
    if _is_cancelled(repository, run):
        raise V020RunError(409, "本次运行已停止；已完成阶段已保留，可稍后继续。")


def _estimate_tokens(value: str) -> int:
    non_ascii = sum(1 for character in value if ord(character) > 127)
    return max(1, non_ascii + ceil((len(value) - non_ascii) / 4))
