from math import ceil

from app.v020_batching import aggregate_usage, response_usage
from app.v020_model_errors import V020RunError
from app.v020_skill_batching import (
    SkillStageBatch, canonicalize_batch_output, merge_stage_outputs, split_batch, stage_batches,
)
from app.v020_skill_contracts import (
    MODEL_STAGES, SKILL_STAGE_COUNT, SKILL_STAGE_OUTPUT_TOKENS, StageDefinition, build_stage_prompt,
)
from app.v020_skill_model_runner import SkillModelRunner
from app.v020_skill_validation import (
    StageOutputInvalid,
    apply_deterministic_stage_repairs,
    ensure_repair_preserves_rows,
    repair_prompt,
    safe_stage_defaults,
    validate_merged_stage,
    validate_stage,
    validation_message,
)


def execute_skill_analysis(model_service, run_repository, resolved, context: dict, preflight: dict, run: dict):
    runner = SkillModelRunner(model_service, run_repository, resolved, run, preflight)
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
        runner.ensure_not_cancelled()
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
            runner.ensure_not_cancelled()
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
            response = runner.call(stage, position, batch, prompt)
            if response.error_code == "provider_response_truncated" and len(batch.scope_ids) > 1:
                queue[0:0] = split_batch(stage, context, artifacts, batch)
                continue
            if response.error_code:
                runner.raise_failure(response)
            if not isinstance(response.raw_output, dict):
                raise V020RunError(502, f"{stage.stage_id} 模型返回内容不是 JSON 对象。")
            candidate = canonicalize_batch_output(
                stage, safe_stage_defaults(stage, response.raw_output), batch,
            )
            candidate, local_repair_applied = apply_deterministic_stage_repairs(
                stage, candidate, batch.context,
            )
            usage = response_usage(response)
            output, usage, repair_applied = _validate_or_repair_batch(
                runner, stage, position, batch, candidate, usage,
            )
            usages.append(usage)
            checkpoint = {
                "checkpoint_type": "skill_batch", "unit": position, "stage_id": stage.stage_id,
                "stage_name": stage.name, "batch_index": batch_number, "scope_ids": list(batch.scope_ids),
                "model_call": True, "local_repair_applied": local_repair_applied,
                "repair_applied": repair_applied, "output": output, "usage": usage,
            }
            run["checkpoints"].append(checkpoint)
            saved_batches.append(checkpoint)
            batch_outputs.append(output)
            run_repository.update_run(run)
        output = merge_stage_outputs(stage, batch_outputs)
        output = validate_merged_stage(stage, output, context, artifacts)
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


def _validate_or_repair_batch(
    runner: SkillModelRunner, stage: StageDefinition, position: int,
    batch: SkillStageBatch, candidate: dict, usage: dict,
) -> tuple[dict, dict, bool]:
    try:
        return validate_stage(stage, candidate, batch.context, batch.artifacts), usage, False
    except StageOutputInvalid as validation_error:
        repair_prompt_value = repair_prompt(
            stage, candidate, validation_error.errors, batch.context, batch.artifacts,
        )
        if _estimate_tokens(repair_prompt_value) + SKILL_STAGE_OUTPUT_TOKENS > 32_000:
            reason = validation_message(stage.stage_id, validation_error.errors, repaired=False)
            raise V020RunError(422, f"{reason} 自动修复请求超过 32k 保守上下文上限。")
        repair_response = runner.call(
            stage,
            position,
            batch,
            repair_prompt_value,
            operation="schema_repair",
            allow_truncated=False,
        )
        if not isinstance(repair_response.raw_output, dict):
            raise V020RunError(502, f"{stage.stage_id} 结构修复返回内容不是 JSON 对象。")
        repaired = canonicalize_batch_output(
            stage, safe_stage_defaults(stage, repair_response.raw_output), batch,
        )
        ensure_repair_preserves_rows(stage, candidate, repaired)
        try:
            output = validate_stage(stage, repaired, batch.context, batch.artifacts)
        except StageOutputInvalid as repair_error:
            raise V020RunError(422, validation_message(stage.stage_id, repair_error.errors, repaired=True))
        return output, aggregate_usage([usage, response_usage(repair_response)]), True


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


def _estimate_tokens(value: str) -> int:
    non_ascii = sum(1 for character in value if ord(character) > 127)
    return max(1, non_ascii + ceil((len(value) - non_ascii) / 4))
