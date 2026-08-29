import hashlib
from datetime import UTC, datetime

from app.requirement_schemas import RequirementVersion, SourceReference
from app.review_schemas import (
    AcceptanceCriterion, AnalyzedRequirement, AnalyzedTestItem, AtomicRequirement,
    RequirementReviewFinding, RequirementConflict, StructuredAnalysisOutput, VisualInference,
)


def build_analysis_candidates(version: RequirementVersion) -> tuple[
    list[AtomicRequirement], list[RequirementReviewFinding], list[VisualInference]
]:
    now = datetime.now(UTC)
    atomic_requirements: list[AtomicRequirement] = []
    findings: list[RequirementReviewFinding] = []
    visual_inferences: list[VisualInference] = []
    for material in version.materials:
        for fragment in material.fragments:
            candidate_id = _identifier("candidate", fragment.source_reference.reference_id)
            atomic_requirements.append(
                AtomicRequirement(
                    candidate_id=candidate_id,
                    statement=fragment.text,
                    source_reference=fragment.source_reference,
                    created_at=now,
                    updated_at=now,
                )
            )
            if "必须" in fragment.text or "不得" in fragment.text:
                findings.append(
                    RequirementReviewFinding(
                        finding_id=_identifier("finding", fragment.source_reference.reference_id),
                        finding_type="missing_acceptance_criteria",
                        summary="该约束需要明确可验证的验收标准",
                        reason="Mock 评审识别到约束性表述，但不会替测试工程师补写验收标准。",
                        source_reference=fragment.source_reference,
                        created_at=now,
                        updated_at=now,
                    )
                )
        for inference in material.visual_inferences:
            visual_inferences.append(
                VisualInference(
                    inference_id=_identifier("visual", inference.source_reference.reference_id),
                    description=inference.description,
                    source_reference=inference.source_reference,
                    created_at=now,
                    updated_at=now,
                )
            )
            findings.append(
                RequirementReviewFinding(
                    finding_id=_identifier("finding-visual", inference.source_reference.reference_id),
                    finding_type="visual_inference_pending",
                    summary="截图中的视觉推断需要人工确认",
                    reason="视觉推断不是需求事实，必须在需求确认前明确采纳或拒绝。",
                    source_reference=inference.source_reference,
                    inference_marker="visual_inference",
                    created_at=now,
                    updated_at=now,
                )
            )
    return atomic_requirements, findings, visual_inferences


def source_reference_exists(version: RequirementVersion, reference: SourceReference) -> bool:
    return any(
        fragment.source_reference.reference_id == reference.reference_id
        and fragment.source_reference.asset_id == reference.asset_id
        for material in version.materials
        for fragment in material.fragments
    ) or any(
        inference.source_reference.reference_id == reference.reference_id
        and inference.source_reference.asset_id == reference.asset_id
        for material in version.materials
        for inference in material.visual_inferences
    )


def semantic_output_to_analysis(
    version: RequirementVersion,
    output: StructuredAnalysisOutput,
) -> tuple[list[AnalyzedRequirement], list[AnalyzedTestItem], list[AcceptanceCriterion],
           list[AtomicRequirement], list[RequirementReviewFinding], list[RequirementConflict]]:
    """校验来源后将模型契约转换为内部评审模型；无效来源不会进入分析结果。"""

    references = {
        reference.reference_id
        for material in version.materials
        for fragment in material.fragments
        for reference in [fragment.source_reference]
    }
    references.update(
        inference.source_reference.reference_id
        for material in version.materials for inference in material.visual_inferences
    )
    all_references = [
        reference
        for material in version.materials
        for fragment in material.fragments
        for reference in [fragment.source_reference]
    ]
    all_references.extend(
        inference.source_reference for material in version.materials for inference in material.visual_inferences
    )
    reference_map = {reference.reference_id: reference for reference in all_references}
    for item in [*output.requirements, *output.test_items, *output.acceptance_criteria]:
        if any(reference.reference_id not in references for reference in item.source_references):
            raise ValueError("模型输出包含不属于当前需求版本的来源引用")
    for finding in output.findings:
        if finding.source_reference.reference_id not in references:
            raise ValueError("模型发现包含不属于当前需求版本的来源引用")
    now = datetime.now(UTC)
    atomics = []
    for requirement in output.requirements:
        source = requirement.source_references[0]
        atomics.append(AtomicRequirement(
            candidate_id=requirement.requirement_id, statement=requirement.statement,
            source_reference=reference_map[source.reference_id], created_at=now, updated_at=now,
        ))
    findings = [RequirementReviewFinding(
        finding_id=item.finding_id, finding_type=item.finding_type, summary=item.summary, reason=item.reason,
        source_reference=reference_map[item.source_reference.reference_id] if item.source_reference else None,
        inference_marker=item.inference_marker, created_at=now, updated_at=now,
    ) for item in output.findings]
    requirements = [requirement.model_copy(update={
        "source_references": [reference_map[item.reference_id] for item in requirement.source_references],
    }) for requirement in output.requirements]
    test_items = [item.model_copy(update={
        "source_references": [reference_map[reference.reference_id] for reference in item.source_references],
    }) for item in output.test_items]
    criteria = [item.model_copy(update={
        "source_references": [reference_map[reference.reference_id] for reference in item.source_references],
    }) for item in output.acceptance_criteria]
    for conflict in output.conflicts:
        if not source_reference_exists(version, conflict.srs_source):
            raise ValueError("冲突 SRS 原文包含不属于当前需求版本的来源引用")
        if not source_reference_exists(version, conflict.implementation_source):
            raise ValueError("冲突实现规格原文包含不属于当前需求版本的来源引用")
    return requirements, test_items, criteria, atomics, findings, output.conflicts


def _identifier(prefix: str, source_id: str) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"
