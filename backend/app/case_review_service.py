from datetime import UTC, datetime

from app.case_review_schemas import (
    CaseRevision, CaseReviewBatch, ReviewGroup, ReviewSuggestion, ReviewerRole, ReviewerRun,
)
from app.case_schemas import CandidateTestCase
from app.design_service import stable_id

ROLES: tuple[ReviewerRole, ...] = ("product_manager", "test_manager", "project_manager")
ROLE_LABELS = {
    "product_manager": "产品经理评审员",
    "test_manager": "测试经理评审员",
    "project_manager": "项目经理评审员",
}


def build_review_batch(
    batch_id: int, project_id: int, generation_id: int, candidates: list[CandidateTestCase], ai_run_ids: dict[str, int],
) -> CaseReviewBatch:
    now = datetime.now(UTC)
    candidate_ids = [candidate.id for candidate in candidates]
    runs = [ReviewerRun(
        role=role, ai_run_id=ai_run_ids[role], candidate_ids=candidate_ids,
        input_context={"candidate_ids": candidate_ids, "allowed_fields": ["title", "objective", "steps", "priority"]},
    ) for role in ROLES]
    suggestions: list[ReviewSuggestion] = []
    for candidate in candidates:
        for role in ROLES:
            suggestion_id = stable_id("review-suggestion", f"{generation_id}:{candidate.id}:{role}")
            suggestions.append(ReviewSuggestion(
                id=suggestion_id, candidate_id=candidate.id, role=role, suggestion_type="supplement",
                summary="补充异常恢复场景的可观察预期", rationale=f"{ROLE_LABELS[role]}建议补充可验证的异常恢复结果。",
                source_references=candidate.requirement_references, limitations=["仅基于候选用例和需求引用，未读取其他评审员输出。"],
                group_id=stable_id("review-group", f"{generation_id}:{candidate.id}:recovery"),
            ))
    groups = _group_suggestions(suggestions)
    return CaseReviewBatch(
        id=batch_id, project_id=project_id, generation_id=generation_id, status="completed", reviewer_runs=runs,
        suggestions=suggestions, groups=groups, created_at=now,
    )


def _group_suggestions(suggestions: list[ReviewSuggestion]) -> list[ReviewGroup]:
    grouped: dict[str, list[ReviewSuggestion]] = {}
    for suggestion in suggestions:
        assert suggestion.group_id is not None
        grouped.setdefault(suggestion.group_id, []).append(suggestion)
    return [ReviewGroup(
        id=group_id, candidate_id=items[0].candidate_id, summary=items[0].summary,
        original_suggestion_ids=[item.id for item in items], source_roles=[item.role for item in items],
    ) for group_id, items in grouped.items()]


def create_revision(batch: CaseReviewBatch, suggestion: ReviewSuggestion, candidate: CandidateTestCase) -> None:
    if suggestion.disposition not in {"accepted", "modified"}:
        return
    revision_number = sum(item.candidate_id == candidate.id for item in batch.revisions) + 1
    revised = candidate.model_copy(deep=True, update=suggestion.modified_fields)
    batch.revisions.append(CaseRevision(
        id=stable_id("case-revision", f"{batch.id}:{candidate.id}:{revision_number}"),
        candidate_id=candidate.id, revision=revision_number, candidate=revised,
        review_notes=[suggestion.summary], created_at=datetime.now(UTC),
    ))
