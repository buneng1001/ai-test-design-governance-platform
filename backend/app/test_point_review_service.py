"""Step 07～08 的确定性测试点审核构造与交接导出。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.design_service import stable_id
from app.review_schemas import RequirementAnalysis
from app.test_point_review_schemas import (
    ReviewTestItem,
    ReviewTestPoint,
    TestPointCoverageCheck,
    TestPointReview,
)


_DIRECTIONS = ("normal", "exception", "boundary", "risk", "permission")
_DIRECTION_LABELS = {
    "normal": "正常场景",
    "exception": "异常处理",
    "boundary": "边界条件",
    "risk": "风险控制",
    "permission": "权限控制",
}
_PERMISSION_MARKERS = ("权限", "角色", "登录", "认证", "授权", "用户")


def build_test_point_review(analysis: RequirementAnalysis) -> TestPointReview:
    """只从已确认、已选择且未被待处置建议阻塞的需求构造审核候选。"""
    pending_ids = {
        requirement_id
        for suggestion in analysis.suggestions
        if suggestion.disposition in {"pending_confirmation", "awaiting_external_confirmation"}
        for requirement_id in suggestion.related_requirement_ids
    }
    selected = set(analysis.selected_requirement_ids)
    requirements = [
        item for item in analysis.atomic_requirements
        if item.decision == "accepted" and item.stable_requirement_id
        and item.candidate_id in selected and item.candidate_id not in pending_ids
    ]
    stable_by_candidate = {item.candidate_id: item.stable_requirement_id for item in requirements}
    accepted_candidates = set(stable_by_candidate)
    test_items: list[ReviewTestItem] = []
    for item in analysis.test_items:
        linked = [requirement_id for requirement_id in item.requirement_ids if requirement_id in accepted_candidates]
        if not linked:
            continue
        test_items.append(ReviewTestItem(
            test_item_id=item.test_item_id,
            name=item.name,
            module=item.module,
            stable_requirement_ids=[stable_by_candidate[requirement_id] for requirement_id in linked],
            source_references=item.source_references,
        ))
    points = [
        _point(analysis, item, direction)
        for item in test_items
        for direction in _directions_for(item)
    ]
    coverage = calculate_coverage(requirements, test_items, points)
    return TestPointReview(
        review_id=stable_id("test-point-review", str(analysis.id)),
        modules=sorted({item.module for item in test_items}),
        test_items=test_items,
        test_points=points,
        coverage_check=coverage,
    )


def calculate_coverage(requirements: list, test_items: list[ReviewTestItem], points: list[ReviewTestPoint]) -> TestPointCoverageCheck:
    """由显式关系复算 Step 08，不依赖模型文字结论。"""
    requirement_ids = {item.stable_requirement_id for item in requirements if item.stable_requirement_id}
    item_by_id = {item.test_item_id: item for item in test_items}
    covered = {requirement_id for point in points for requirement_id in point.stable_requirement_ids}
    uncovered = sorted(requirement_ids - covered)
    isolated = sorted(
        point.platform_test_point_id for point in points
        if point.test_item_id not in item_by_id
        or not set(point.stable_requirement_ids).intersection(item_by_id[point.test_item_id].stable_requirement_ids)
    )
    linked_items = {point.test_item_id for point in points}
    missing_items = sorted(item.test_item_id for item in test_items if item.test_item_id not in linked_items)
    direction_gaps = {
        item.test_item_id: [direction for direction in _directions_for(item)
                             if direction not in {point.direction for point in points if point.test_item_id == item.test_item_id}]
        for item in test_items
    }
    direction_gaps = {item_id: gaps for item_id, gaps in direction_gaps.items() if gaps}
    return TestPointCoverageCheck(
        passed=not uncovered and not isolated and not missing_items and not direction_gaps,
        total_confirmed_requirement_count=len(requirement_ids),
        covered_requirement_count=len(covered.intersection(requirement_ids)),
        uncovered_requirement_ids=uncovered,
        isolated_test_point_ids=isolated,
        missing_test_item_ids=missing_items,
        direction_gaps=direction_gaps,
    )


def save_selection(review: TestPointReview, test_item_ids: list[str], test_point_ids: list[str]) -> TestPointReview:
    if review.status == "confirmed":
        raise ValueError("审核确认后不能修改生成范围")
    known_items = {item.test_item_id for item in review.test_items}
    known_points = {item.platform_test_point_id for item in review.test_points}
    unknown_items = sorted(set(test_item_ids) - known_items)
    unknown_points = sorted(set(test_point_ids) - known_points)
    if unknown_items or unknown_points:
        raise ValueError("生成范围包含不存在的测试项或测试点")
    review.selected_test_item_ids = sorted(set(test_item_ids))
    review.selected_test_point_ids = sorted(set(test_point_ids))
    return review


def selected_test_points(review: TestPointReview) -> list[ReviewTestPoint]:
    selected_items = set(review.selected_test_item_ids)
    selected_points = set(review.selected_test_point_ids)
    return [
        point for point in review.test_points
        if point.test_item_id in selected_items or point.platform_test_point_id in selected_points
    ]


def confirm_review(review: TestPointReview, confirmer_name: str) -> TestPointReview:
    if not review.coverage_check.passed:
        raise ValueError("Step 08 覆盖自检未通过，不能确认审核")
    review.status = "confirmed"
    review.handoff_version = f"{review.review_id}-handoff-v1"
    review.confirmed_by = confirmer_name
    review.confirmed_at = datetime.now(UTC)
    return review


def export_markdown_package(analysis: RequirementAnalysis) -> str:
    """导出只含分析边界和审核交接的 Step 00～08 兼容 Markdown 包。"""
    review = analysis.test_point_review
    if review is None:
        raise ValueError("请先生成 Step 07～08 审核结果")
    lines = [
        "# Step 00～08 需求到测试点分析包",
        "",
        "## Step 00～02 已确认需求",
        "",
        *[f"- {item.stable_requirement_id}: {item.statement}" for item in analysis.atomic_requirements
          if item.decision == "accepted" and item.stable_requirement_id],
        "",
        "## Step 03～06 建议处置",
        "",
        *[f"- {item.suggestion_id}: {item.disposition}" for item in analysis.suggestions],
        "",
        "## Step 07 测试项与测试点",
        "",
        *[f"- {point.skill_test_point_id} ↔ {point.platform_test_point_id}: {point.objective}"
          f"（测试项 {point.test_item_id}；需求 {', '.join(point.stable_requirement_ids)}）"
          for point in review.test_points],
        "",
        "## Step 08 覆盖自检",
        "",
        f"- 通过：{'是' if review.coverage_check.passed else '否'}",
        f"- 覆盖需求：{review.coverage_check.covered_requirement_count}/{review.coverage_check.total_confirmed_requirement_count}",
        f"- 已选测试点：{len(selected_test_points(review))}",
        f"- 交接版本：{review.handoff_version or '未确认'}",
    ]
    return "\n".join(lines) + "\n"


def _point(analysis: RequirementAnalysis, item: ReviewTestItem, direction: str) -> ReviewTestPoint:
    rules = [
        criterion.criterion_id for criterion in analysis.acceptance_criteria
        if criterion.requirement_id in {
            atomic.candidate_id for atomic in analysis.atomic_requirements
            if atomic.stable_requirement_id in item.stable_requirement_ids
        }
    ]
    platform_id = stable_id("test-point", f"{item.test_item_id}:{direction}")
    return ReviewTestPoint(
        skill_test_point_id=f"S07-TP-{platform_id.removeprefix('test-point-')}",
        platform_test_point_id=platform_id,
        test_item_id=item.test_item_id,
        stable_requirement_ids=item.stable_requirement_ids,
        rule_ids=rules,
        source_references=item.source_references,
        direction=direction,
        objective=f"验证{item.name}在{_DIRECTION_LABELS[direction]}下的已确认行为",
    )


def _directions_for(item: ReviewTestItem) -> tuple[str, ...]:
    text = f"{item.name} {item.module}"
    return _DIRECTIONS if any(marker in text for marker in _PERMISSION_MARKERS) else _DIRECTIONS[:-1]
