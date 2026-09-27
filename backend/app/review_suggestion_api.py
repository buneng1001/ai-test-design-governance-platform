"""新增建议的生成、人工处置和补充需求再确认接口。"""

import hashlib
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException

from app.main_route_context import AppRouteContext
from app.requirement_review_api import require_review
from app.review_repository import RequirementReviewRepository
from app.review_schemas import (
    RequirementAnalysis, SupplementalRequirementCandidate, SupplementalRequirementConfirmationInput,
    SuggestionDispositionInput,
)
from app.review_suggestion_service import build_review_suggestions


def register_review_suggestion_routes(app: FastAPI, context: AppRouteContext) -> None:
    """注册 Step 03～06 路由，不覆盖已经确认的需求基线。"""
    repository = context.repository
    reviews: RequirementReviewRepository = context.review_repository

    @app.post(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/suggestions/generate",
        response_model=RequirementAnalysis,
    )
    def generate_suggestions(project_id: int, analysis_id: int) -> RequirementAnalysis:
        analysis = require_review(repository, reviews, project_id, analysis_id)
        if analysis.status != "confirmed":
            raise HTTPException(status_code=409, detail="请先确认需求后再生成新增建议")
        if not analysis.selected_requirement_ids:
            raise HTTPException(status_code=409, detail="请至少确认一条进入分析范围的需求")
        if not analysis.suggestions:
            analysis.suggestions = build_review_suggestions(analysis)
            return reviews.save(analysis, "review_suggestions_generated")
        return analysis

    @app.patch(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/suggestions/{suggestion_id}",
        response_model=RequirementAnalysis,
    )
    def dispose_suggestion(
        project_id: int, analysis_id: int, suggestion_id: str, update: SuggestionDispositionInput
    ) -> RequirementAnalysis:
        analysis = require_review(repository, reviews, project_id, analysis_id)
        suggestion = next((item for item in analysis.suggestions if item.suggestion_id == suggestion_id), None)
        if suggestion is None:
            raise HTTPException(status_code=404, detail="新增建议不存在")
        suggestion.disposition = update.disposition
        if update.statement is not None:
            suggestion.statement = update.statement
        suggestion.updated_at = datetime.now(UTC)
        if update.disposition in {"accepted", "modified"} and suggestion.proposed_requirement_statement:
            _create_supplemental_candidate(analysis, suggestion.suggestion_id, update.statement or suggestion.proposed_requirement_statement)
        return reviews.save(analysis, "review_suggestion_disposed")

    @app.post(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/supplemental-requirements/confirm",
        response_model=RequirementAnalysis,
    )
    def confirm_supplemental_requirements(
        project_id: int, analysis_id: int, confirmation: SupplementalRequirementConfirmationInput
    ) -> RequirementAnalysis:
        analysis = require_review(repository, reviews, project_id, analysis_id)
        candidates = {item.candidate_id: item for item in analysis.supplemental_requirement_candidates}
        if any(candidate_id not in candidates for candidate_id in confirmation.candidate_ids):
            raise HTTPException(status_code=422, detail="补充需求确认包含不存在的候选")
        now = datetime.now(UTC)
        for candidate_id in confirmation.candidate_ids:
            candidate = candidates[candidate_id]
            if candidate.decision == "confirmed":
                raise HTTPException(status_code=409, detail="补充需求已经确认")
            candidate.decision = "confirmed"
            candidate.stable_requirement_id = f"REQ-SUP-{candidate.candidate_id.removeprefix('supplemental-')}"
            candidate.confirmed_by = confirmation.confirmer_name
            candidate.confirmed_at = now
            candidate.updated_at = now
        return reviews.save(analysis, "supplemental_requirements_confirmed")


def _create_supplemental_candidate(analysis: RequirementAnalysis, suggestion_id: str, statement: str) -> None:
    candidate_id = f"supplemental-{hashlib.sha256(suggestion_id.encode()).hexdigest()[:12]}"
    if any(item.candidate_id == candidate_id for item in analysis.supplemental_requirement_candidates):
        return
    suggestion = next(item for item in analysis.suggestions if item.suggestion_id == suggestion_id)
    now = datetime.now(UTC)
    analysis.supplemental_requirement_candidates.append(SupplementalRequirementCandidate(
        candidate_id=candidate_id,
        statement=statement,
        source_references=suggestion.source_references,
        related_requirement_ids=suggestion.related_requirement_ids,
        created_at=now,
        updated_at=now,
    ))
