"""v0.2.0 工作流 Skill 的结构化契约适配层。

本模块只校验阶段产物和 Skill 之间的交接，不保存业务对象，也不替代现有
需求、测试设计或候选用例领域模型。后续工作流适配器应在持久化前调用它。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.case_schemas import TestStep


CONTRACT_VERSION = "ai-test-design-workflow.v1"
STAGE_IDS = tuple(f"S{number:02d}" for number in range(9))
Priority = Literal["P0", "P1", "P2", "P3"]
StageStatus = Literal["completed", "needs_information", "failed"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class TestPoint(BaseModel):
    """Step 07 的轻量交接对象，只描述测什么而不包含详细步骤。"""

    model_config = ConfigDict(extra="forbid")

    skill_test_point_id: Annotated[str, StringConstraints(pattern=r"^S07-TP-[A-Za-z0-9_-]+$")]
    platform_test_point_id: Text
    test_item_id: Text
    stable_requirement_ids: list[Text] = Field(min_length=1)
    rule_ids: list[Text] = Field(default_factory=list)
    direction: Literal["normal", "exception", "boundary", "risk", "permission"]
    objective: Text


class AnalysisStageArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: Literal["S00", "S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08"]
    status: StageStatus
    input_version: Text
    output_version: Text
    prompt_version: Text
    template_version: Text
    output: dict[str, object] = Field(default_factory=dict)
    missing_information: list[Text] = Field(default_factory=list)
    failure_code: Text | None = None

    @model_validator(mode="after")
    def validate_terminal_fields(self) -> "AnalysisStageArtifact":
        if self.status == "completed" and (self.missing_information or self.failure_code):
            raise ValueError("完成的阶段不能同时声明信息不足或模型失败")
        if self.status == "needs_information" and not self.missing_information:
            raise ValueError("信息不足阶段必须说明缺失信息")
        if self.status == "failed" and not self.failure_code:
            raise ValueError("失败阶段必须提供失败代码")
        if self.stage_id == "S07" and self.status == "completed":
            parse_test_points(self.output.get("test_points"))
        if self.stage_id == "S08" and self.status == "completed":
            CoverageCheck.model_validate(self.output.get("coverage_check"))
        return self


def parse_test_points(value: object) -> list[TestPoint]:
    if not isinstance(value, list) or not value:
        raise ValueError("必须提供非空列表")
    return [TestPoint.model_validate(item) for item in value]


class RequirementAnalysisRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[CONTRACT_VERSION]
    run_id: Text
    test_object: Text
    software_version: Text
    stages: list[AnalysisStageArtifact] = Field(min_length=1, max_length=9)

    @model_validator(mode="after")
    def validate_stage_sequence(self) -> "RequirementAnalysisRun":
        stage_indexes = [STAGE_IDS.index(stage.stage_id) for stage in self.stages]
        if stage_indexes != list(range(len(self.stages))):
            raise ValueError("阶段必须从 S00 开始连续执行，不能跳过或重排")
        terminal_stages = [stage for stage in self.stages if stage.status != "completed"]
        if terminal_stages:
            if len(terminal_stages) != 1 or self.stages[-1] is not terminal_stages[0]:
                raise ValueError("信息不足或失败必须停止后续阶段")
        elif len(self.stages) != len(STAGE_IDS):
            raise ValueError("正常完成必须包含 S00 至 S08")
        return self

    def step07_handoff(self) -> "Step07Handoff":
        stage = next((item for item in self.stages if item.stage_id == "S07"), None)
        coverage_stage = next((item for item in self.stages if item.stage_id == "S08"), None)
        if stage is None or stage.status != "completed":
            raise ValueError("只有已完成的 Step 07 才能交接给用例生成")
        if coverage_stage is None or coverage_stage.status != "completed":
            raise ValueError("只有通过 Step 08 覆盖自检的分析运行才能交接")
        if not CoverageCheck.model_validate(coverage_stage.output.get("coverage_check")).passed:
            raise ValueError("Step 08 覆盖自检未通过，不能交接给用例生成")
        points = parse_test_points(stage.output.get("test_points"))
        return Step07Handoff(
            contract_version=self.contract_version,
            analysis_run_id=self.run_id,
            software_version=self.software_version,
            test_points=points,
        )


class Step07Handoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[CONTRACT_VERSION]
    analysis_run_id: Text
    software_version: Text
    test_points: list[TestPoint] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_stable_point_mapping(self) -> "Step07Handoff":
        skill_ids = {point.skill_test_point_id for point in self.test_points}
        platform_ids = {point.platform_test_point_id for point in self.test_points}
        if len(skill_ids) != len(self.test_points) or len(platform_ids) != len(self.test_points):
            raise ValueError("Skill 测试点编号与平台测试点 ID 必须一对一映射")
        return self


class CoverageCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    uncovered_requirement_ids: list[Text] = Field(default_factory=list)
    isolated_test_point_ids: list[Text] = Field(default_factory=list)


class CandidateCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_case_id: Text
    title: Text
    objective: Text
    preconditions: list[Text] = Field(min_length=1)
    test_input: Text
    steps: list[TestStep] = Field(min_length=1)
    overall_expectation: Text
    evidence_requirements: list[Text] = Field(min_length=1)
    design_basis: list[Text] = Field(min_length=1)
    software_version: Text
    priority: Priority
    skill_test_point_id: Text
    platform_test_point_id: Text
    test_item_id: Text
    stable_requirement_ids: list[Text] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_step_order(self) -> "CandidateCase":
        if [step.order for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("用例步骤编号必须从 1 连续递增")
        return self


class CaseGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[CONTRACT_VERSION]
    analysis_run_id: Text
    prompt_version: Text
    template_version: Text
    status: Literal["completed", "needs_information", "failed"]
    candidates: list[CandidateCase] = Field(default_factory=list)
    missing_information: list[Text] = Field(default_factory=list)
    failure_code: Text | None = None

    @model_validator(mode="after")
    def validate_result_state(self) -> "CaseGenerationResult":
        if self.status == "completed" and not self.candidates:
            raise ValueError("完成的用例生成必须返回候选用例")
        if self.status != "completed" and self.candidates:
            raise ValueError("信息不足或失败不能伪装为成功候选用例")
        if self.status == "needs_information" and not self.missing_information:
            raise ValueError("信息不足结果必须说明缺失信息")
        if self.status == "failed" and not self.failure_code:
            raise ValueError("失败结果必须提供失败代码")
        return self


def validate_case_generation(
    handoff: Step07Handoff | dict[str, object], result: CaseGenerationResult | dict[str, object],
) -> CaseGenerationResult:
    """校验候选用例只能引用同一 Step 07 交接中已确认的测试点和需求。"""

    parsed_handoff = Step07Handoff.model_validate(handoff)
    parsed_result = CaseGenerationResult.model_validate(result)
    if parsed_result.contract_version != parsed_handoff.contract_version:
        raise ValueError("用例生成结果与 Step 07 使用的契约版本不兼容")
    if parsed_result.analysis_run_id != parsed_handoff.analysis_run_id:
        raise ValueError("用例生成结果必须关联同一需求分析运行")
    point_by_skill_id = {point.skill_test_point_id: point for point in parsed_handoff.test_points}
    if len(point_by_skill_id) != len(parsed_handoff.test_points):
        raise ValueError("Step 07 测试点编号必须唯一")
    candidate_ids: set[str] = set()
    for candidate in parsed_result.candidates:
        if candidate.candidate_case_id in candidate_ids:
            raise ValueError("候选用例编号必须唯一")
        candidate_ids.add(candidate.candidate_case_id)
        point = point_by_skill_id.get(candidate.skill_test_point_id)
        if point is None:
            raise ValueError("候选用例引用了不存在的 Step 07 测试点")
        if (candidate.platform_test_point_id, candidate.test_item_id) != (
            point.platform_test_point_id, point.test_item_id,
        ):
            raise ValueError("候选用例的测试点平台映射不一致")
        if not set(candidate.stable_requirement_ids).issubset(point.stable_requirement_ids):
            raise ValueError("候选用例引用了测试点之外的稳定需求")
        if candidate.software_version != parsed_handoff.software_version:
            raise ValueError("候选用例的软件版本必须继承 Step 07 交接")
    return parsed_result
