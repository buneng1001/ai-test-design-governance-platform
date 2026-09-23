from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.workflow_contracts import CONTRACT_VERSION, RequirementAnalysisRun, validate_case_generation


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _completed_stages() -> list[dict]:
    stages = []
    for number in range(9):
        stage = {
            "stage_id": f"S{number:02d}", "status": "completed", "input_version": "input.v1",
            "output_version": "output.v1", "prompt_version": "prompt.v1", "template_version": "template.v1",
            "output": {},
        }
        if number == 7:
            stage["output"] = {"test_points": [{
                "skill_test_point_id": "S07-TP-001", "platform_test_point_id": "test-point-001",
                "test_item_id": "test-item-001", "stable_requirement_ids": ["REQ-001"],
                "rule_ids": ["RULE-001"], "direction": "boundary", "objective": "验证已确认条件",
            }]}
        if number == 8:
            stage["output"] = {"coverage_check": {"passed": True}}
        stages.append(stage)
    return stages


def _normal_analysis_run() -> RequirementAnalysisRun:
    return RequirementAnalysisRun.model_validate({
        "contract_version": CONTRACT_VERSION, "run_id": "analysis-run-001", "test_object": "合成测试对象",
        "software_version": "v0", "stages": _completed_stages(),
    })


def _candidate(priority: str = "P3") -> dict:
    return {
        "candidate_case_id": "candidate-001", "title": "验证已确认条件", "objective": "确认边界行为",
        "preconditions": ["满足前置状态"], "test_input": "边界输入",
        "steps": [{"order": 1, "action": "执行操作", "input": "边界输入", "expected": "得到可验证结果"}],
        "overall_expectation": "整体结果符合已确认规则", "evidence_requirements": ["结果记录"],
        "design_basis": ["边界值方法"], "software_version": "v0", "priority": priority,
        "skill_test_point_id": "S07-TP-001", "platform_test_point_id": "test-point-001",
        "test_item_id": "test-item-001", "stable_requirement_ids": ["REQ-001"],
    }


def test_project_skills_are_versioned_and_self_contained() -> None:
    for name in ("ai-test-design-requirement-analysis", "ai-test-design-case-generation"):
        skill = REPOSITORY_ROOT / "skills" / name / "SKILL.md"
        assert skill.is_file()
        contents = skill.read_text(encoding="utf-8")
        assert f"name: {name}" in contents
        assert "工作区外" in contents
        assert "P0" in contents and "P3" in contents


def test_normal_analysis_handoff_and_all_priorities_pass_structure_validation() -> None:
    analysis = _normal_analysis_run()
    handoff = analysis.step07_handoff()
    for priority in ("P0", "P1", "P2", "P3"):
        result = {
            "contract_version": CONTRACT_VERSION, "analysis_run_id": analysis.run_id, "status": "completed",
            "prompt_version": "case-prompt.v1", "template_version": "case-template.v1",
            "candidates": [_candidate(priority)],
        }
        assert validate_case_generation(handoff, result).candidates[0].priority == priority


def test_information_insufficient_stops_analysis_and_never_creates_candidates() -> None:
    run = RequirementAnalysisRun.model_validate({
        "contract_version": CONTRACT_VERSION, "run_id": "analysis-run-002", "test_object": "合成测试对象",
        "software_version": "v0", "stages": [
            {"stage_id": "S00", "status": "completed", "input_version": "input.v1", "output_version": "output.v1",
             "prompt_version": "prompt.v1", "template_version": "template.v1"},
            {"stage_id": "S01", "status": "needs_information", "input_version": "input.v1",
             "output_version": "output.v1", "prompt_version": "prompt.v1", "template_version": "template.v1",
             "missing_information": ["缺少可确认的材料"], "output": {}},
        ],
    })
    with pytest.raises(ValueError, match="Step 07"):
        run.step07_handoff()
    with pytest.raises(ValidationError, match="不能伪装为成功"):
        validate_case_generation({
            "contract_version": CONTRACT_VERSION, "analysis_run_id": run.run_id, "software_version": "v0",
            "test_points": [
                {"skill_test_point_id": "S07-TP-001", "platform_test_point_id": "test-point-001",
                 "test_item_id": "test-item-001", "stable_requirement_ids": ["REQ-001"],
                 "direction": "normal", "objective": "验证"}
            ],
        }, {"contract_version": CONTRACT_VERSION, "analysis_run_id": run.run_id,
            "status": "needs_information", "prompt_version": "case-prompt.v1", "template_version": "case-template.v1",
            "candidates": [_candidate()], "missing_information": ["缺少材料"]})


def test_model_failure_stops_stage_and_invalid_mapping_is_rejected() -> None:
    with pytest.raises(ValidationError, match="停止后续阶段"):
        RequirementAnalysisRun.model_validate({
            "contract_version": CONTRACT_VERSION, "run_id": "analysis-run-003", "test_object": "合成测试对象",
            "software_version": "v0", "stages": [
                {"stage_id": "S00", "status": "failed", "input_version": "input.v1", "output_version": "output.v1",
                 "prompt_version": "prompt.v1", "template_version": "template.v1", "failure_code": "model_unavailable"},
                {"stage_id": "S01", "status": "completed", "input_version": "input.v1", "output_version": "output.v1",
                 "prompt_version": "prompt.v1", "template_version": "template.v1"},
            ],
        })
    analysis = _normal_analysis_run()
    bad_candidate = deepcopy(_candidate())
    bad_candidate["platform_test_point_id"] = "another-test-point"
    with pytest.raises(ValueError, match="平台映射不一致"):
        validate_case_generation(analysis.step07_handoff(), {
            "contract_version": CONTRACT_VERSION, "analysis_run_id": analysis.run_id, "status": "completed",
            "prompt_version": "case-prompt.v1", "template_version": "case-template.v1",
            "candidates": [bad_candidate],
        })


def test_step08_and_one_to_one_mapping_are_required_before_case_generation() -> None:
    incomplete_coverage = _normal_analysis_run().model_copy(deep=True)
    incomplete_coverage.stages[-1].output = {"coverage_check": {"passed": False}}
    with pytest.raises(ValueError, match="覆盖自检未通过"):
        incomplete_coverage.step07_handoff()
    duplicate_mapping = _normal_analysis_run().step07_handoff().model_copy(deep=True)
    duplicate_mapping.test_points.append(duplicate_mapping.test_points[0].model_copy(update={
        "skill_test_point_id": "S07-TP-002",
    }))
    with pytest.raises(ValidationError, match="一对一映射"):
        type(duplicate_mapping).model_validate(duplicate_mapping.model_dump())


def test_valid_model_failure_result_passes_structure_validation_without_candidates() -> None:
    analysis = _normal_analysis_run()
    failed = validate_case_generation(analysis.step07_handoff(), {
        "contract_version": CONTRACT_VERSION, "analysis_run_id": analysis.run_id, "status": "failed",
        "prompt_version": "case-prompt.v1", "template_version": "case-template.v1",
        "failure_code": "model_unavailable",
    })
    assert failed.candidates == []
