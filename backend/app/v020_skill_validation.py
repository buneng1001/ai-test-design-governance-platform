import json
from copy import deepcopy

from app.v020_contracts import MAX_SKILL_STAGE_ANALYSIS_ROWS, TEST_TYPES
from app.v020_model_errors import V020RunError
from app.v020_run_schemas import AnalysisOutputRow
from app.v020_skill_contracts import SKILL_PROMPT_VERSION, StageDefinition


class StageOutputInvalid(Exception):
    def __init__(self, stage_id: str, errors: list[dict]) -> None:
        self.stage_id = stage_id
        self.errors = errors
        super().__init__(validation_message(stage_id, errors, repaired=False))


def validate_stage(stage: StageDefinition, raw: dict, context: dict, artifacts: dict[str, dict]) -> dict:
    try:
        parsed = stage.model.model_validate(raw)
    except ValueError as error:
        raise StageOutputInvalid(stage.stage_id, error.errors()) from error
    output = parsed.model_dump(mode="json")
    return _validate_references(stage, output, context, artifacts)


def _validate_references(stage: StageDefinition, output: dict, context: dict, artifacts: dict[str, dict]) -> dict:
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
    batch_requirement_ids = {
        item["requirement_id"] for item in artifacts.get("S00", {}).get("atomic_requirements", [])
    }
    if stage.stage_id in {"S01", "S02"}:
        requirement_ids = {
            item["requirement_id"] for item in context.get("global_requirement_index", [])
        } or batch_requirement_ids
        key = "functions" if stage.stage_id == "S01" else "rules"
        if any(set(item["requirement_ids"]) - requirement_ids for item in output[key]):
            raise V020RunError(422, f"{stage.stage_id} 输出引用了不存在的原子需求 ID。")
    if stage.stage_id in {"S03", "S04", "S05", "S06"}:
        if any(item["source_reference_id"] not in sources for item in output["rows"]):
            raise V020RunError(422, f"{stage.stage_id} 输出引用了资料范围外的来源。")
        if any(item["related_requirement_id"] not in batch_requirement_ids for item in output["rows"]):
            raise V020RunError(422, f"{stage.stage_id} 输出引用了不存在的原子需求 ID。")
    return output


def validate_merged_stage(stage: StageDefinition, raw: dict, context: dict, artifacts: dict[str, dict]) -> dict:
    """合并结果使用阶段总量上限；单批仍受 StageRowsOutput 的 500 行契约约束。"""
    if stage.stage_id not in {"S03", "S04", "S05", "S06"}:
        return validate_stage(stage, raw, context, artifacts)
    rows = raw.get("rows") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or len(rows) > MAX_SKILL_STAGE_ANALYSIS_ROWS:
        raise StageOutputInvalid(stage.stage_id, [{
            "loc": ("rows",), "type": "stage_row_limit",
        }])
    try:
        output = {"rows": [AnalysisOutputRow.model_validate(row).model_dump(mode="json") for row in rows]}
    except ValueError as error:
        raise StageOutputInvalid(stage.stage_id, error.errors()) from error
    return _validate_references(stage, output, context, artifacts)


def safe_stage_defaults(stage: StageDefinition, raw: dict) -> dict:
    candidate = deepcopy(raw)
    if stage.stage_id == "S04" and isinstance(candidate.get("rows"), list):
        for row in candidate["rows"]:
            if isinstance(row, dict):
                row.setdefault("test_type", "异常测试")
    return candidate


def apply_deterministic_stage_repairs(
    stage: StageDefinition, candidate: dict, context: dict,
) -> tuple[dict, bool]:
    """只补全可由已有 ID 关系确定推导的字段，不生成新的业务内容。"""
    if stage.stage_id != "S00" or isinstance(candidate.get("source_coverage"), list):
        return candidate, False
    requirements = candidate.get("atomic_requirements")
    if not isinstance(requirements, list):
        return candidate, False
    source_ids = [item["source_reference_id"] for item in context.get("fragments", [])]
    requirements_by_source: dict[str, list[str]] = {source_id: [] for source_id in source_ids}
    for item in requirements:
        if not isinstance(item, dict):
            return candidate, False
        source_id = item.get("source_reference_id")
        requirement_id = item.get("requirement_id")
        if source_id not in requirements_by_source or not isinstance(requirement_id, str):
            return candidate, False
        requirements_by_source[source_id].append(requirement_id)
    if not source_ids:
        return candidate, False
    repaired = deepcopy(candidate)
    repaired["source_coverage"] = [{
        "source_reference_id": source_id,
        "requirement_ids": requirements_by_source[source_id],
        "no_requirement_reason": (
            "" if requirements_by_source[source_id]
            else "当前模型输出未从该来源提取原子需求，需人工复核"
        ),
    } for source_id in source_ids]
    questions = list(repaired.get("questions", [])) if isinstance(repaired.get("questions"), list) else []
    questions.extend(
        f"请复核 {source_id} 是否确实不包含可测试需求。"
        for source_id in source_ids if not requirements_by_source[source_id]
    )
    repaired["questions"] = list(dict.fromkeys(questions))
    return repaired, True


def repair_prompt(
    stage: StageDefinition, invalid_output: dict, errors: list[dict], context: dict, artifacts: dict[str, dict],
) -> str:
    compact_errors = [{"path": ".".join(map(str, item.get("loc", ()))), "type": item.get("type", "invalid")}
                      for item in errors[:100]]
    allowed_requirements = (
        context.get("global_requirement_index", [])
        if stage.stage_id in {"S01", "S02"}
        else artifacts.get("S00", {}).get("atomic_requirements", [])
    )
    repair_context: dict[str, object] = {
        "allowed_source_reference_ids": [item["source_reference_id"] for item in context["fragments"]],
        "allowed_requirement_ids": [item["requirement_id"] for item in allowed_requirements],
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


def ensure_repair_preserves_rows(stage: StageDefinition, before: dict, after: dict) -> None:
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


def validation_message(stage_id: str, errors: list[dict], *, repaired: bool) -> str:
    missing: dict[str, int] = {}
    invalid: dict[str, int] = {}
    for item in errors:
        target = missing if item.get("type") == "missing" and item.get("loc") else invalid
        field = str(item.get("loc", ("结构",))[-1])
        target[field] = target.get(field, 0) + 1
    details = []
    if missing:
        details.append("缺少字段 " + "、".join(f"{field}（{count} 处）" for field, count in sorted(missing.items())))
    if invalid:
        details.append("字段或结构不合法 " + "、".join(
            f"{field}（{count} 处）" for field, count in sorted(invalid.items())
        ))
    phase = "一次结构修复后仍" if repaired else ""
    return f"{stage_id} 模型输出{phase}不符合字段契约：{'；'.join(details) or '结构不合法'}。"
