"""候选用例的可复算质量检查及平台标准交付表。"""
from __future__ import annotations

import csv
import io
from collections import Counter

from app.case_lifecycle_service import _build_xlsx
from app.case_review_schemas import CaseRevision
from app.review_schemas import RequirementAnalysis
from app.test_point_review_service import selected_test_points


STANDARD_COLUMNS = [
    "stable_case_id", "priority", "software_version", "steps", "step_expectations",
    "overall_expectation", "evidence_requirements", "design_basis", "traceability", "source",
]


def current_revisions(revisions: list[CaseRevision]) -> list[CaseRevision]:
    latest: dict[str, CaseRevision] = {}
    for revision in revisions:
        if revision.stable_case_id is None:
            continue
        previous = latest.get(revision.stable_case_id)
        if previous is None or revision.revision > previous.revision:
            latest[revision.stable_case_id] = revision
    return [item for item in latest.values() if item.lifecycle_status == "effective"
            and item.participation_status == "included"]


def standard_rows(revisions: list[CaseRevision]) -> list[dict[str, str]]:
    rows = []
    for revision in current_revisions(revisions):
        candidate = revision.candidate
        rows.append({
            "stable_case_id": revision.stable_case_id or "",
            "priority": candidate.priority,
            "software_version": candidate.software_version,
            "steps": _numbered([(step.action, step.input) for step in candidate.steps]),
            "step_expectations": _numbered([(step.expected, "") for step in candidate.steps]),
            "overall_expectation": candidate.overall_expectation,
            "evidence_requirements": "；".join(candidate.evidence_requirements),
            "design_basis": "；".join(f"{item.method}：{item.reason}" for item in candidate.design_basis),
            "traceability": "；".join(candidate.requirement_ids + [
                reference.reference_id for reference in candidate.requirement_references
            ]),
            "source": "template_fallback" if candidate.template_fallback else "standard",
        })
    return rows


def export_standard(rows: list[dict[str, str]], output_format: str) -> tuple[bytes, str, str]:
    values = [STANDARD_COLUMNS, *[[row[column] for column in STANDARD_COLUMNS] for row in rows]]
    if output_format == "csv":
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerows(values)
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "csv"
    return (_build_xlsx([("平台标准用例表", values)]),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx")


def quality_report(review: RequirementAnalysis, revisions: list[CaseRevision]) -> dict:
    cases = current_revisions(revisions)
    accepted_requirement_ids = {
        item.stable_requirement_id for item in review.atomic_requirements
        if item.decision == "accepted" and item.stable_requirement_id
    }
    selected_point_models = selected_test_points(review.test_point_review) if review.test_point_review else []
    selected_points = {item.platform_test_point_id for item in selected_point_models}
    selected_requirements = {
        requirement_id for point in selected_point_models for requirement_id in point.stable_requirement_ids
    }
    accepted_requirements = accepted_requirement_ids & selected_requirements
    case_requirement_ids = {item for case in cases for item in case.candidate.requirement_ids}
    case_point_ids = {case.candidate.platform_test_point_id for case in cases if case.candidate.platform_test_point_id}
    issues: list[dict[str, str]] = []
    for requirement_id in sorted(accepted_requirements - case_requirement_ids):
        issues.append(_issue("orphan_requirement", requirement_id, "已确认需求没有当前纳入用例"))
    for point_id in sorted(selected_points - case_point_ids):
        issues.append(_issue("orphan_test_point", point_id, "已选测试点没有当前纳入用例"))
    fingerprints = Counter((case.candidate.title.strip(), case.candidate.objective.strip()) for case in cases)
    for case in cases:
        candidate = case.candidate
        if fingerprints[(candidate.title.strip(), candidate.objective.strip())] > 1:
            issues.append(_issue("duplicate_case", case.stable_case_id or candidate.id, "标题和测试目标重复"))
        missing = _missing_fields(case)
        if missing:
            issues.append(_issue("missing_field", case.stable_case_id or candidate.id, "缺少：" + "、".join(missing)))
        invalid = [item for item in candidate.requirement_ids if item not in accepted_requirements]
        if invalid or not candidate.requirement_references or not candidate.platform_test_point_id:
            issues.append(_issue("invalid_reference", case.stable_case_id or candidate.id, "需求或测试点追踪引用无效"))
        if [step.order for step in candidate.steps] != list(range(1, len(candidate.steps) + 1)):
            issues.append(_issue("non_continuous_steps", case.stable_case_id or candidate.id, "步骤编号必须从 1 连续递增"))
        if _unverifiable(candidate.overall_expectation) or any(_unverifiable(step.expected) for step in candidate.steps):
            issues.append(_issue("unverifiable_expectation", case.stable_case_id or candidate.id, "预期结果缺少可观察或可判定条件"))
    return {
        "coverage": {
            "requirements": _coverage(accepted_requirements, case_requirement_ids),
            "test_items": _coverage(
                {item.test_item_id for item in selected_point_models},
                {case.candidate.test_item for case in cases},
            ),
            "test_points": _coverage(selected_points, case_point_ids),
            "cases": {"numerator": len(cases), "denominator": len(cases), "percentage": 100.0 if cases else 0.0},
        },
        "issues": issues,
    }


def _numbered(items: list[tuple[str, str]]) -> str:
    return "\n".join(f"{index}. {first}{('：' + second) if second else ''}" for index, (first, second) in enumerate(items, 1))


def _coverage(expected: set[str], actual: set[str]) -> dict[str, object]:
    covered = expected & actual
    return {"numerator": len(covered), "denominator": len(expected),
            "percentage": round(100 * len(covered) / len(expected), 2) if expected else 100.0,
            "uncovered": sorted(expected - actual)}


def _missing_fields(case: CaseRevision) -> list[str]:
    candidate = case.candidate
    fields = {"稳定用例 ID": case.stable_case_id, "优先级": candidate.priority,
              "软件版本": candidate.software_version, "前置条件": candidate.preconditions,
              "步骤": candidate.steps, "整体预期": candidate.overall_expectation,
              "证据要求": candidate.evidence_requirements, "设计依据": candidate.design_basis}
    return [label for label, value in fields.items() if not value]


def _unverifiable(value: str) -> bool:
    text = value.strip()
    observable = ("显示", "返回", "状态", "保存", "记录", "日志", "提示", "包含", "等于", "拒绝", "允许", "生成", "更新", "响应", "数值", "文件")
    return not text or not any(marker in text for marker in observable)


def _issue(rule: str, target_id: str, message: str) -> dict[str, str]:
    return {"rule": rule, "target_id": target_id, "message": message, "severity": "warning"}
