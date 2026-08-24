import hashlib
from datetime import UTC, datetime

from app.requirement_schemas import RequirementVersion, SourceReference
from app.review_schemas import AtomicRequirement, RequirementReviewFinding, VisualInference


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


def _identifier(prefix: str, source_id: str) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"
