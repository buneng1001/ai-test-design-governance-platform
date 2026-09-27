"""详细测试用例生成的模型边界：契约校验、Prompt 和确定性 Mock。"""

import json
from typing import Any

from pydantic import ValidationError

from app.case_schemas import CaseGenerationModelOutput


def validate_case_generation_output(
    raw_output: object, allowed_test_point_ids: set[str],
) -> tuple[dict | None, list[str]]:
    try:
        output = CaseGenerationModelOutput.model_validate(raw_output)
    except ValidationError as error:
        return None, [
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()[:10]
        ]
    unknown_points = sorted({item.test_point_id for item in output.items} - allowed_test_point_ids)
    errors = []
    if unknown_points:
        errors.append(f"模型输出包含未选择或无法追踪的测试点：{', '.join(unknown_points)}")
    return (None, errors) if errors else (output.model_dump(mode="json"), [])


def case_generation_prompt(input_context: tuple[dict[str, object], ...]) -> str:
    return (
        "请针对当前测试设计任务输出 case-generation.v1 JSON。每项必须包含 test_point_id、variant、"
        "case_discriminator、title、objective、preconditions、steps（order/action/input/expected）、"
        "overall_expectation、evidence_requirements、design_basis（method/reason）和 pending_confirmations。"
        "case_discriminator 必须表达同一测试点下可重复识别的边界值、等价类或场景标识。"
        "标题、目标、前置条件、输入、步骤、逐步预期和整体预期必须由你基于给定测试点实际生成；"
        "只使用给定测试点及其需求、验收条件、规则、来源摘要和软件版本。未知阈值或行为写入 "
        "pending_confirmations，不能作为需求事实断言。只输出 JSON，不得输出 Markdown、API Key 或清单外测试点。"
        + json.dumps(input_context, ensure_ascii=False, separators=(",", ":"))
    )


def build_mock_case_generation(input_context: tuple[dict[str, object], ...]) -> dict[str, object]:
    """Mock 也遵守详细用例生成契约，供离线演示和 CI 验证完整字段。"""
    items = []
    for point in input_context:
        direction = str(point.get("direction", "normal"))
        variant = {
            "normal": "normal", "boundary": "boundary", "exception": "invalid",
            "risk": "scenario", "permission": "normal",
        }.get(direction, "normal")
        objective = str(point.get("objective", "验证已确认测试点"))
        labels = {"normal": "正常路径", "boundary": "边界条件", "invalid": "异常输入", "scenario": "风险场景"}
        method = {"normal": "scenario", "boundary": "boundary", "invalid": "equivalence", "scenario": "risk_based"}[variant]
        items.append({
            "test_point_id": point.get("platform_test_point_id"), "variant": variant,
            "case_discriminator": f"{variant}-{point.get('platform_test_point_id')}",
            "title": f"{objective} - {labels[variant]}", "objective": objective,
            "preconditions": [f"测试对象处于可验证{objective}的初始状态"],
            "steps": [
                {"order": 1, "action": "准备测试对象", "input": f"按{labels[variant]}准备输入", "expected": "测试对象接受准备状态"},
                {"order": 2, "action": "执行目标能力", "input": objective, "expected": "系统返回与输入对应的可观察结果"},
            ],
            "overall_expectation": f"{objective}完成后，系统行为符合已确认原子需求。",
            "evidence_requirements": ["保留关键操作截图或请求响应", "记录最终状态和必要日志"],
            "design_basis": [{"method": method, "reason": f"按{labels[variant]}拆分为可独立确认和执行的用例。"}],
            "pending_confirmations": [],
        })
    return {"contract_version": "case-generation.v1", "items": items}
