from datetime import UTC, datetime

from app.case_schemas import CaseDesignBasis, CandidateTestCase, CaseVariant, TestStep
from app.design_schemas import DesignAsset, RiskAssessment, TestScopeItem
from app.requirement_schemas import RequirementVersion, SourceReference
from app.review_schemas import RequirementAnalysis
from app.template_schemas import TemplateMappingVersion
from app.design_service import stable_id

SUPPORTED_TEMPLATE_FIELDS = {
    "external_case_number", "title", "objective", "preconditions", "steps", "step_expectations",
    "overall_expectation", "evidence_requirements", "priority",
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
    variants: list[CaseVariant],
    limitations: list[dict],
) -> list[CandidateTestCase]:
    case_sheet = next(sheet for sheet in mapping.sheets if sheet.role == "case" and sheet.participates)
    requirements = {
        item.stable_requirement_id: item for item in review.atomic_requirements if item.decision == "accepted"
    }
    risks = {item.scope_item_id: item for item in design.risks}
    automations = {item.scope_item_id: item for item in design.automation_candidates}
    candidates: list[CandidateTestCase] = []
    for scope in design.scope_items:
        linked = [requirements[item] for item in scope.requirement_ids if item in requirements]
        risk = risks.get(scope.id)
        if not linked or risk is None:
            continue
        references = [item.source_reference for item in linked]
        for variant in variants:
            candidate_id = stable_id("candidate-case", f"{project_id}:{scope.id}:{variant}")
            candidates.append(_candidate(
                candidate_id, generation_id, project_id, scope, risk, automations.get(scope.id), variant,
                references, case_sheet.name, limitations,
            ))
    return candidates


def _candidate(
    candidate_id: str, generation_id: int, project_id: int, scope: TestScopeItem, risk: RiskAssessment,
    automation: object, variant: CaseVariant, references: list[SourceReference], sheet_name: str,
    limitations: list[dict],
) -> CandidateTestCase:
    labels = {"normal": "正常路径", "boundary": "边界值", "equivalence": "等价类", "invalid": "非法输入", "scenario": "异常场景"}
    label = labels[variant]
    return CandidateTestCase(
        id=candidate_id, project_id=project_id, generation_id=generation_id,
        title=f"{scope.title} - {label}", objective=f"验证{scope.title}在{label}下满足已确认需求。", variant=variant,
        preconditions=[f"测试对象处于可验证{scope.title}的初始状态"],
        steps=[
            TestStep(order=1, action="准备测试对象", input=f"按{label}准备输入", expected="测试对象接受准备状态"),
            TestStep(order=2, action="执行目标能力", input=scope.description, expected="系统返回与输入对应的可观察结果"),
        ],
        overall_expectation=f"{scope.title}完成后，系统行为符合已确认原子需求。",
        evidence_requirements=["保留关键操作截图或请求响应", "记录最终状态和必要日志"],
        requirement_ids=scope.requirement_ids, requirement_references=references, scope_item_id=scope.id,
        risk_item_id=f"risk-{scope.id}", priority=risk.priority, case_sheet_name=sheet_name,
        automation_mapping=f"automation-{scope.id}" if automation is not None else None,
        unexpressed_fields=[item.get("code", "unknown") for item in limitations],
        design_basis=[CaseDesignBasis(
            method="boundary" if variant == "boundary" else "equivalence" if variant == "equivalence" else "scenario",
            reason=f"按{label}拆分为可独立确认和执行的用例。", source_references=references,
        )],
        created_at=datetime.now(UTC),
    )
