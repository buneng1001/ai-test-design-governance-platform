import json
from dataclasses import dataclass
from math import ceil

from pydantic import BaseModel, ConfigDict, Field

from app.ai_schemas import AIModelConfig
from app.ai_service import ModelRequest
from app.v020_batching import aggregate_usage, response_usage
from app.v020_contracts import TEST_TYPES
from app.v020_model_errors import V020RunError, model_failure
from app.v020_run_schemas import AnalysisOutputRow, NonEmptyText


SKILL_PROMPT_VERSION = "requirement-analysis.skill.v5"
SKILL_STAGE_OUTPUT_TOKENS = 4_000
SKILL_STAGE_COUNT = 9


class AtomicRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: NonEmptyText
    statement: NonEmptyText
    source_reference_id: NonEmptyText


class Stage00Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    atomic_requirements: list[AtomicRequirement] = Field(min_length=1, max_length=300)
    questions: list[str] = Field(default_factory=list, max_length=100)


class IdentifiedFunction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    function_id: NonEmptyText
    module: NonEmptyText
    name: NonEmptyText
    description: NonEmptyText
    requirement_ids: list[NonEmptyText] = Field(min_length=1, max_length=100)


class Stage01Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    functions: list[IdentifiedFunction] = Field(min_length=1, max_length=300)


class BusinessRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: NonEmptyText
    description: NonEmptyText
    requirement_ids: list[NonEmptyText] = Field(min_length=1, max_length=100)


class Stage02Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[BusinessRule] = Field(default_factory=list, max_length=500)


class StageRowsOutput(BaseModel):
    """某一分析方向可以没有适用项，避免模型为满足契约而机械凑数。"""

    model_config = ConfigDict(extra="forbid")
    rows: list[AnalysisOutputRow] = Field(default_factory=list, max_length=500)


@dataclass(frozen=True)
class StageDefinition:
    stage_id: str
    name: str
    instruction: str
    output_contract: str
    model: type[BaseModel]


MODEL_STAGES = (
    StageDefinition(
        "S00", "材料基线与原子需求", "逐条提取资料中的原子需求，不扩写资料没有表达的功能。",
        '{"atomic_requirements":[{"requirement_id":"REQ-001","statement":"...",'
        '"source_reference_id":"input-1"}],"questions":[]}', Stage00Output,
    ),
    StageDefinition(
        "S01", "功能识别", "基于原子需求识别宽泛业务模块及其功能，保留需求 ID 关联。",
        '{"functions":[{"function_id":"FUN-001","module":"...","name":"...",'
        '"description":"...","requirement_ids":["REQ-001"]}]}', Stage01Output,
    ),
    StageDefinition(
        "S02", "业务规则提取", "提取状态、阈值、前置条件、限制、异常处理和验收条件。",
        '{"rules":[{"rule_id":"RULE-001","description":"...",'
        '"requirement_ids":["REQ-001"]}]}', Stage02Output,
    ),
    StageDefinition(
        "S03", "正常场景构建", "只构建正常、主流程、冒烟和基础功能测试项。", "", StageRowsOutput,
    ),
    StageDefinition(
        "S04", "异常场景构建", "只构建异常、失败分支、错误处理和恢复相关测试项。", "", StageRowsOutput,
    ),
    StageDefinition(
        "S05", "边界场景构建", "只构建数值、容量、时间、状态转换和输入边界测试项。", "", StageRowsOutput,
    ),
    StageDefinition(
        "S06", "风险与专项补全", "只补充权限、安全、性能、兼容、稳定性及适用专项测试项。", "", StageRowsOutput,
    ),
)


def skill_preflight_prompts(context: dict) -> list[str]:
    """预检只能按最小上游产物估算；运行时会对每个实际阶段再次检查。"""
    placeholders = {
        "S00": {"atomic_requirements": [], "questions": []},
        "S01": {"functions": []},
        "S02": {"rules": []},
    }
    return [build_stage_prompt(stage, context, placeholders) for stage in MODEL_STAGES]


def build_stage_prompt(stage: StageDefinition, context: dict, artifacts: dict[str, dict]) -> str:
    row_contract = (
        '{"rows":[{"module":"宽泛业务模块","test_item":"可验证测试项",'
        '"test_basis":"资料依据与分析理由","source_reference_id":"input-1",'
        '"test_type":"功能测试","priority":"P1","related_requirement_id":"REQ-001"}]}'
    )
    prior = {key: value for key, value in artifacts.items() if key in _prior_stage_ids(stage.stage_id)}
    payload = {
        "project": {"test_object": context["test_object"], "software_version": context["software_version"]},
        "supplemental_notes": context.get("supplemental_notes", ""),
        "input_metadata": {
            "material_understanding_used": context.get("material_understanding_used", False),
            "material_understanding_run_id": context.get("material_understanding_run_id"),
        },
        "materials": context["fragments"],
        "prior_stage_outputs": prior,
    }
    return (
        f"提示版本：{SKILL_PROMPT_VERSION}.{stage.stage_id.lower()}。\n"
        f"当前阶段：{stage.stage_id} {stage.name}。{stage.instruction}\n"
        "每个阶段都针对同一份完整资料执行，并使用所需的上游阶段产物。"
        "必须以 materials 和已给出的上游阶段产物为依据；ID 必须原样复用，禁止补造来源。\n"
        f"输出契约：{stage.output_contract or row_contract}\n"
        f"test_type 仅可从以下分类中选择：{'、'.join(TEST_TYPES)}；priority 仅可使用 P0、P1、P2、P3。"
        "只输出 JSON 对象，不要输出解释、Markdown 或 API Key。\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


def execute_skill_analysis(model_service, run_repository, resolved, context: dict, preflight: dict, run: dict):
    checkpoints = {item.get("stage_id"): item for item in run.get("checkpoints", []) if item.get("stage_id")}
    artifacts = {stage_id: item["output"] for stage_id, item in checkpoints.items() if "output" in item}
    usages = [item["usage"] for item in checkpoints.values() if item.get("model_call") and item.get("usage")]
    for position, stage in enumerate(MODEL_STAGES, start=1):
        if stage.stage_id in artifacts:
            continue
        _ensure_not_cancelled(run_repository, run)
        _set_progress(run_repository, run, position - 1, stage, "调用模型")
        prompt = build_stage_prompt(stage, context, artifacts)
        if _estimate_tokens(prompt) + SKILL_STAGE_OUTPUT_TOKENS > 32_000:
            raise V020RunError(
                422, f"{stage.stage_id} 的完整资料、上游产物与预留输出合计超过 32k 保守上下文上限；"
                "请缩小资料范围后重试。",
            )
        response = None
        for attempt in range(1, 3):
            _ensure_not_cancelled(run_repository, run)
            response = model_service.complete(ModelRequest(
                task_type="requirement_review", prompt_version=f"{SKILL_PROMPT_VERSION}.{stage.stage_id.lower()}",
                model_parameters=AIModelConfig(provider=resolved.provider, model=resolved.model, temperature=0,
                                               max_tokens=SKILL_STAGE_OUTPUT_TOKENS),
                input_asset_versions=(), scenario="normal", base_url=resolved.base_url, api_key=resolved.api_key,
                prompt_override=prompt, network_mode=resolved.network_mode,
                cancel_requested=lambda: _is_cancelled(run_repository, run),
            ))
            run["attempts"].append({
                "unit": position, "stage_id": stage.stage_id, "attempt": attempt,
                "error_code": response.error_code, "duration_ms": response.duration_ms,
                "first_event_ms": response.first_event_ms, "finish_reason": response.finish_reason,
                "response_length": response.response_length, "diagnostic": response.diagnostic,
            })
            run_repository.update_run(run)
            if not response.error_code or not response.retryable or attempt == 2:
                break
        assert response is not None
        if response.error_code == "provider_cancelled":
            raise V020RunError(409, "本次运行已停止；已完成阶段已保留，可稍后继续。")
        if response.error_code:
            status, detail = model_failure(response, preflight["provider"], preflight["model"], "analysis")
            raise V020RunError(status, detail)
        if not isinstance(response.raw_output, dict):
            raise V020RunError(502, f"{stage.stage_id} 模型返回内容不是 JSON 对象。")
        output = _validate_stage(stage, response.raw_output, context, artifacts)
        usage = response_usage(response)
        artifacts[stage.stage_id] = output
        usages.append(usage)
        run["checkpoints"].append({
            "unit": position, "stage_id": stage.stage_id, "stage_name": stage.name,
            "model_call": True, "output": output, "usage": usage,
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


def _validate_stage(stage: StageDefinition, raw: dict, context: dict, artifacts: dict[str, dict]) -> dict:
    try:
        parsed = stage.model.model_validate(raw)
    except ValueError as error:
        raise V020RunError(422, f"{stage.stage_id} 输出结构校验失败：{str(error)[:400]}") from error
    output = parsed.model_dump(mode="json")
    sources = {item["source_reference_id"] for item in context["fragments"]}
    if stage.stage_id == "S00":
        if any(item["source_reference_id"] not in sources for item in output["atomic_requirements"]):
            raise V020RunError(422, "S00 输出引用了资料范围外的来源。")
        ids = [item["requirement_id"] for item in output["atomic_requirements"]]
        if len(ids) != len(set(ids)):
            raise V020RunError(422, "S00 原子需求 ID 必须唯一。")
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


def _prior_stage_ids(stage_id: str) -> set[str]:
    return {"S01": {"S00"}, "S02": {"S00", "S01"},
            "S03": {"S00", "S01", "S02"}, "S04": {"S00", "S01", "S02"},
            "S05": {"S00", "S01", "S02"}, "S06": {"S00", "S01", "S02"}}.get(stage_id, set())


def _set_progress(repository, run: dict, completed: int, stage: StageDefinition, status: str) -> None:
    run["stage"] = f"{stage.stage_id} {stage.name} · {status}"
    run["progress"] = {"completed_units": completed, "total_units": SKILL_STAGE_COUNT, "stage": run["stage"]}
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
