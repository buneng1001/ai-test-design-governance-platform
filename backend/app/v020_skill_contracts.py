import json
from dataclasses import dataclass
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.v020_contracts import TEST_TYPES
from app.v020_run_schemas import AnalysisOutputRow, NonEmptyText


SKILL_PROMPT_VERSION = "requirement-analysis.skill.v6"
SKILL_STAGE_OUTPUT_TOKENS = 4_000
SKILL_STAGE_COUNT = 9


class AtomicRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: NonEmptyText
    statement: NonEmptyText
    source_reference_id: NonEmptyText


class SourceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_reference_id: NonEmptyText
    requirement_ids: list[NonEmptyText] = Field(default_factory=list, max_length=100)
    no_requirement_reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def require_result_or_reason(self) -> Self:
        if bool(self.requirement_ids) == bool(self.no_requirement_reason.strip()):
            raise ValueError("每个来源必须关联至少一个需求，或填写无需求原因，不能同时填写")
        return self


class Stage00Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    atomic_requirements: list[AtomicRequirement] = Field(min_length=1, max_length=300)
    source_coverage: list[SourceCoverage] = Field(min_length=1, max_length=200)
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
        '"source_reference_id":"input-1"}],"source_coverage":[{"source_reference_id":"input-1",'
        '"requirement_ids":["REQ-001"],"no_requirement_reason":""}],"questions":[]}', Stage00Output,
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
    StageDefinition("S03", "正常场景构建", "只构建正常、主流程、冒烟和基础功能测试项。", "", StageRowsOutput),
    StageDefinition("S04", "异常场景构建", "只构建异常、失败分支、错误处理和恢复相关测试项。", "", StageRowsOutput),
    StageDefinition("S05", "边界场景构建", "只构建数值、容量、时间、状态转换和输入边界测试项。", "", StageRowsOutput),
    StageDefinition("S06", "风险与专项补全", "只补充权限、安全、性能、兼容、稳定性及适用专项测试项。", "", StageRowsOutput),
)


def skill_preflight_prompts(context: dict) -> list[str]:
    """预检只能按最小上游产物估算；运行时会对每个实际阶段再次检查。"""
    placeholders = {
        "S00": {"atomic_requirements": [], "source_coverage": [], "questions": []},
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
    row_constraints = ""
    if stage.stage_id in {"S03", "S04", "S05", "S06"}:
        row_constraints = (
            f"test_type 仅可从以下分类中选择：{'、'.join(TEST_TYPES)}；"
            "priority 仅可使用 P0、P1、P2、P3。"
            "每个测试项必须包含契约中的全部七个字段，任何字段都不能省略。"
        )
    return (
        f"提示版本：{SKILL_PROMPT_VERSION}.{stage.stage_id.lower()}。\n"
        f"当前阶段：{stage.stage_id} {stage.name}。{stage.instruction}\n"
        "每个阶段都针对同一份完整资料执行，并使用所需的上游阶段产物。"
        "必须以 materials 和已给出的上游阶段产物为依据；ID 必须原样复用，禁止补造来源。\n"
        f"输出契约：{stage.output_contract or row_contract}\n"
        + ("S00 的 source_coverage 必须逐一覆盖 materials 中每个 source_reference_id；"
           "有需求时列出该来源对应的全部 requirement_ids，没有需求时 requirement_ids 为空并填写明确原因。\n"
           if stage.stage_id == "S00" else "")
        + row_constraints
        + "只输出 JSON 对象，不要输出解释、Markdown 或 API Key。\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


def _prior_stage_ids(stage_id: str) -> set[str]:
    return {"S01": {"S00"}, "S02": {"S00", "S01"},
            "S03": {"S00", "S01", "S02"}, "S04": {"S00", "S01", "S02"},
            "S05": {"S00", "S01", "S02"}, "S06": {"S00", "S01", "S02"}}.get(stage_id, set())
