from datetime import UTC, datetime

from app.case_schemas import CaseDesignBasis, CandidateTestCase, CaseGenerationOutputItem
from app.design_schemas import DesignAsset, RiskAssessment, TestScopeItem
from app.requirement_schemas import RequirementVersion, SourceReference
from app.review_schemas import RequirementAnalysis
from app.test_point_review_schemas import ReviewTestPoint
from app.template_schemas import TemplateMappingVersion
from app.design_service import stable_id

SUPPORTED_TEMPLATE_FIELDS = {
    "external_case_number", "title", "objective", "preconditions", "steps", "step_expectations",
    "overall_expectation", "evidence_requirements", "priority", "input", "test_type", "module", "test_item",
    "test_result", "test_record", "pre_test_notes", "planned_execution_time", "attachment", "software_version",
}


def template_limitations(mapping: TemplateMappingVersion) -> list[dict]:
    limitations = [
        diagnostic.model_dump()
        for diagnostic in mapping.diagnostics
        if diagnostic.code in {"unsupported_semantics", "formula_loss", "image_loss", "merged_cells", "pivot_loss"}
    ] + [
        diagnostic.model_dump()
        for sheet in mapping.sheets
        for diagnostic in sheet.diagnostics
        if diagnostic.code in {"unsupported_semantics", "formula_loss", "image_loss", "merged_cells", "pivot_loss"}
    ]
    for sheet in mapping.sheets:
        for field in sheet.field_mapping.values():
            if field not in SUPPORTED_TEMPLATE_FIELDS:
                limitations.append({
                    "code": "unsupported_semantics", "severity": "warning",
                    "message": f"无法无损表达内部语义：{field}", "sheet_name": sheet.name,
                })
    return limitations


def build_candidates(
    generation_id: int,
    project_id: int,
    design: DesignAsset,
    review: RequirementAnalysis,
    version: RequirementVersion,
    mapping: TemplateMappingVersion,
    limitations: list[dict],
    generated_items: list[dict],
    selected_requirement_ids: list[str] | None = None,
    excluded_modules: set[str] | None = None,
    included_modules: set[str] | None = None,
    software_version: str = "",
    selected_test_points: list[ReviewTestPoint] | None = None,
    template_fallback: bool = False,
) -> list[CandidateTestCase]:
    case_sheet = next(sheet for sheet in mapping.sheets if sheet.role == "case" and sheet.participates)
    selected = set(selected_requirement_ids) if selected_requirement_ids is not None else None
    excluded = excluded_modules or set()
    requirements = {
        item.stable_requirement_id: item for item in review.atomic_requirements
        if item.decision == "accepted" and (
            selected is None or item.candidate_id in selected or item.stable_requirement_id in selected
        )
    }
    requirement_modules = {item.requirement_id: item.module for item in review.requirements}
    risks = {item.scope_item_id: item for item in design.risks}
    automations = {item.scope_item_id: item for item in design.automation_candidates}
    points = {point.platform_test_point_id: point for point in selected_test_points or []}
    test_items = {
        item.test_item_id: item for item in (review.test_point_review.test_items if review.test_point_review else [])
    }
    candidates: list[CandidateTestCase] = []
    for raw_item in generated_items:
        item = CaseGenerationOutputItem.model_validate(raw_item)
        point = points[item.test_point_id]
        scope = next((scope for scope in design.scope_items
                      if set(point.stable_requirement_ids).intersection(scope.requirement_ids)), None)
        if scope is None:
            raise ValueError(f"测试点 {point.platform_test_point_id} 没有有效的测试范围项")
        point_requirements = [
            requirement for requirement in requirements.values()
            if requirement.stable_requirement_id in point.stable_requirement_ids
            and requirement_modules.get(requirement.candidate_id) not in excluded
        ]
        if included_modules and not any(
            requirement_modules.get(requirement.candidate_id) in included_modules for requirement in point_requirements
        ):
            continue
        risk = risks.get(scope.id)
        if not point_requirements or risk is None:
            raise ValueError(f"测试点 {point.platform_test_point_id} 的追踪关系不完整")
        references = [requirement.source_reference for requirement in point_requirements]
        test_item = test_items.get(point.test_item_id)
        candidate_key = stable_id(
            "candidate-key", f"{point.platform_test_point_id}:{item.variant}:{item.case_discriminator}"
        )
        candidate_id = stable_id("candidate-case", f"{project_id}:{scope.id}:{candidate_key}")
        candidates.append(_candidate(
            candidate_id, candidate_key, generation_id, project_id, scope, risk, automations.get(scope.id), item,
            references, case_sheet.name, limitations, software_version, point,
            test_item.module if test_item else "", template_fallback,
        ))
    return candidates


def _candidate(
    candidate_id: str, candidate_key: str, generation_id: int, project_id: int, scope: TestScopeItem, risk: RiskAssessment,
    automation: object, generated: CaseGenerationOutputItem, references: list[SourceReference], sheet_name: str,
    limitations: list[dict], software_version: str, test_point: ReviewTestPoint, module: str, template_fallback: bool,
) -> CandidateTestCase:
    return CandidateTestCase(
        id=candidate_id, candidate_key=candidate_key, project_id=project_id, generation_id=generation_id,
        title=generated.title, objective=generated.objective, variant=generated.variant,
        preconditions=generated.preconditions, steps=generated.steps,
        overall_expectation=generated.overall_expectation, evidence_requirements=generated.evidence_requirements,
        requirement_ids=test_point.stable_requirement_ids, requirement_references=references, scope_item_id=scope.id,
        risk_item_id=f"risk-{scope.id}", priority=risk.priority, case_sheet_name=sheet_name,
        automation_mapping=f"automation-{scope.id}" if automation is not None else None,
        unexpressed_fields=[item.get("code", "unknown") for item in limitations],
        design_basis=[CaseDesignBasis(**basis.model_dump(), source_references=references) for basis in generated.design_basis],
        created_at=datetime.now(UTC),
        input=generated.steps[0].input,
        module=module,
        test_item=test_point.test_item_id,
        software_version=software_version,
        platform_test_point_id=test_point.platform_test_point_id,
        skill_test_point_id=test_point.skill_test_point_id,
        template_fallback=template_fallback,
        pending_confirmations=generated.pending_confirmations,
    )


def _case_generation_context(
    review: RequirementAnalysis, selected_points: list[ReviewTestPoint], software_version: str,
) -> tuple[dict[str, object], ...]:
    """向模型只提供用户已选测试点及其最小、可追溯的生成上下文。"""
    atomic_by_stable_id = {
        item.stable_requirement_id: item for item in review.atomic_requirements
        if item.decision == "accepted" and item.stable_requirement_id
    }
    test_items = {item.test_item_id: item for item in review.test_point_review.test_items}
    candidate_to_stable = {
        item.candidate_id: item.stable_requirement_id for item in review.atomic_requirements
        if item.stable_requirement_id
    }
    rules_by_requirement: dict[str, list[dict[str, str]]] = {}
    for criterion in review.acceptance_criteria:
        stable_requirement_id = candidate_to_stable.get(criterion.requirement_id, criterion.requirement_id)
        rules_by_requirement.setdefault(stable_requirement_id, []).append({
            "rule_id": criterion.criterion_id, "statement": criterion.statement,
        })
    return tuple({
        "platform_test_point_id": point.platform_test_point_id,
        "skill_test_point_id": point.skill_test_point_id,
        "test_item": {
            "id": point.test_item_id,
            "name": test_items[point.test_item_id].name,
            "module": test_items[point.test_item_id].module,
        },
        "stable_requirement_ids": point.stable_requirement_ids,
        "requirements": [{
            "stable_requirement_id": requirement_id,
            "statement": atomic_by_stable_id[requirement_id].statement,
            "source": atomic_by_stable_id[requirement_id].source_reference.model_dump(mode="json"),
            "acceptance_criteria": [rule["statement"] for rule in rules_by_requirement.get(requirement_id, [])],
        } for requirement_id in point.stable_requirement_ids if requirement_id in atomic_by_stable_id],
        "rules": [
            rule for requirement_id in point.stable_requirement_ids
            for rule in rules_by_requirement.get(requirement_id, []) if rule["rule_id"] in point.rule_ids
        ],
        "source_summaries": [reference.model_dump(mode="json") for reference in point.source_references],
        "direction": point.direction,
        "objective": point.objective,
        "software_version": software_version,
    } for point in selected_points)
