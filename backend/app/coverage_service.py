from collections.abc import Iterable

from app.case_review_schemas import CaseReviewBatch, CaseRevision
from app.design_schemas import DesignAsset, RiskAssessment, TestDimension
from app.execution_batch_schemas import ExecutionBatch
from app.execution_result_schemas import ExecutionResultRecord
from app.review_schemas import RequirementAnalysis


def build_coverage(
    review: RequirementAnalysis | None,
    design: DesignAsset | None,
    cases: CaseReviewBatch | None,
    batch: ExecutionBatch | None,
    results: list[ExecutionResultRecord],
    quality_issues: Iterable[dict],
    open_conflict_result_ids: set[int] | None = None,
) -> dict:
    # 覆盖事实只来自已确认需求、设计、用例和可匹配的执行记录。
    confirmed_cases = _confirmed_cases(cases)
    confirmed_requirements = review.atomic_requirements if review and review.status == "confirmed" else []
    requirements = [item.stable_requirement_id for item in confirmed_requirements
                    if item.decision == "accepted" and item.stable_requirement_id]
    requirement_case_ids = {item: _cases_for_requirement(confirmed_cases, item) for item in requirements}
    confirmed_design = design if design and design.status == "confirmed" else None
    risks = [item for item in (confirmed_design.risks if confirmed_design else [])]
    risk_case_ids = {item.scope_item_id: _cases_for_scope(confirmed_cases, item.scope_item_id) for item in risks}
    dimensions = [item for item in (confirmed_design.dimensions if confirmed_design else []) if item.status == "active"]
    dimension_case_ids = {
        item.id: _cases_for_dimension(confirmed_cases, confirmed_design, item.id) for item in dimensions
    }
    batch_cases = [item.stable_case_id for item in (batch.cases if batch else [])]
    valid_result_cases = {
        record.stable_case_id for record in results
        if record.match_status == "matched"
        and record.id not in (open_conflict_result_ids or set())
        and record.stable_case_id in set(batch_cases)
    }
    execution_details = {case_id: [case_id] if case_id in valid_result_cases else [] for case_id in batch_cases}
    automated_scope_ids = {
        item.scope_item_id for item in (confirmed_design.automation_candidates if confirmed_design else [])
        if item.decision in {"priority_automation", "suitable_automation", "conditional_automation"}
    }
    automated_cases = [item for item in confirmed_cases if item.candidate.scope_item_id in automated_scope_ids]
    automated_result_cases = {
        record.stable_case_id for record in results
        if record.match_status == "matched"
        and record.id not in (open_conflict_result_ids or set())
        and record.stable_case_id in {item.stable_case_id for item in automated_cases}
        and record.source_type != "manual"
    }
    metrics = {
        "requirement_coverage": _metric(requirement_case_ids, "需求"),
        "risk_coverage": _metric(risk_case_ids, "风险", high_ids={item.scope_item_id for item in risks
                                                                     if item.risk_level == "high"}),
        "dimension_coverage": _metric(dimension_case_ids, "测试维度"),
        "execution_coverage": _metric(execution_details, "执行用例"),
        "automation_coverage": _metric(
            {item.stable_case_id: ([item.stable_case_id] if item.stable_case_id in automated_result_cases else [])
             for item in automated_cases if item.stable_case_id},
            "自动化用例",
        ),
    }
    relationship_sets = [requirement_case_ids, risk_case_ids, dimension_case_ids,
                         execution_details, {
                             item.stable_case_id: ([item.stable_case_id]
                                                    if item.stable_case_id in automated_result_cases else [])
                             for item in automated_cases if item.stable_case_id
                         }]
    for metric, relationships_for_metric in zip(metrics.values(), relationship_sets):
        related_case_ids = {case_id for case_ids in relationships_for_metric.values() for case_id in case_ids}
        metric["quality_issues"] = [
            issue for issue in quality_issues if issue.get("stable_case_id") in related_case_ids
        ]
        metric["execution_evidence"] = [
            record.model_dump(mode="json") for record in results
            if record.stable_case_id in related_case_ids
        ]
    return {"metrics": metrics}


def _metric(relationships: dict[str, list[str]], label: str, high_ids: set[str] | None = None) -> dict:
    covered = [key for key, related in relationships.items() if related]
    uncovered = [key for key, related in relationships.items() if not related]
    denominator = len(relationships)
    return {
        "label": label,
        "numerator": len(covered),
        "denominator": denominator,
        "percentage": round(len(covered) / denominator * 100, 2) if denominator else 100.0,
        "covered_items": covered,
        "uncovered_items": uncovered,
        "high_risk_gaps": sorted((high_ids or set()) & set(uncovered)),
    }


def _confirmed_cases(batch: CaseReviewBatch | None) -> list[CaseRevision]:
    if batch is None or batch.status != "confirmed":
        return []
    return [
        item for item in batch.revisions
        if item.stable_case_id and item.lifecycle_status == "effective" and item.participation_status == "included"
    ]


def _cases_for_requirement(cases: list[CaseRevision], requirement_id: str) -> list[str]:
    return [item.stable_case_id for item in cases if requirement_id in item.candidate.requirement_ids]


def _cases_for_scope(cases: list[CaseRevision], scope_id: str) -> list[str]:
    return [item.stable_case_id for item in cases if item.candidate.scope_item_id == scope_id]


def _cases_for_dimension(cases: list[CaseRevision], design: DesignAsset | None, dimension_id: str) -> list[str]:
    if design is None:
        return []
    scope_ids = {
        item.id for item in design.scope_items
        if item.primary_dimension_id == dimension_id or dimension_id in item.secondary_dimension_ids
    }
    return [item.stable_case_id for item in cases if item.candidate.scope_item_id in scope_ids]
