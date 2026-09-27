"""Step 03～06 建议的确定性构造，输入仅限已确认且已选择的需求。"""

import hashlib
from datetime import UTC, datetime

from app.review_schemas import RequirementAnalysis, ReviewSuggestion


def build_review_suggestions(analysis: RequirementAnalysis) -> list[ReviewSuggestion]:
    selected = set(analysis.selected_requirement_ids)
    requirements = [item for item in analysis.requirements if item.requirement_id in selected]
    if not requirements:
        return []
    now = datetime.now(UTC)
    suggestions: list[ReviewSuggestion] = []
    directions = (
        ("normal", "missing_acceptance_criteria", "analysis_inference", "补充正常场景的可验证结果，确保已确认需求在满足前置条件时可复核。", None),
        ("exception", "missing_constraint_or_error_handling", "analysis_inference", "补充异常输入或失败处理的预期，避免异常路径只依赖隐含假设。", None),
        ("boundary", "omission", "analysis_inference", "补充边界条件的明确约束或验收标准，避免阈值和极值由测试人员猜测。", "请明确边界条件、允许值和超界后的处理规则。"),
        ("risk", "dependency_unclear", "awaiting_confirmation", "确认依赖不可用、状态中断或恢复失败时的风险处置与可观察结果。", "请明确依赖异常或恢复失败时的降级、提示和恢复要求。"),
    )
    for requirement in requirements:
        for direction, problem_type, source_type, statement, proposed in directions:
            suggestion_id = _suggestion_id(analysis.id, requirement.requirement_id, direction)
            suggestions.append(ReviewSuggestion(
                suggestion_id=suggestion_id,
                direction=direction,
                problem_type=problem_type,
                statement=f"{requirement.name}：{statement}",
                source_type=source_type,
                source_references=requirement.source_references,
                related_requirement_ids=[requirement.requirement_id],
                impact_scope=f"模块：{requirement.module}；需求：{requirement.name}",
                proposed_requirement_statement=proposed,
                created_at=now,
                updated_at=now,
            ))
    return suggestions


def _suggestion_id(analysis_id: int, requirement_id: str, direction: str) -> str:
    digest = hashlib.sha256(f"{analysis_id}:{requirement_id}:{direction}".encode()).hexdigest()[:12]
    return f"suggestion-{digest}"
