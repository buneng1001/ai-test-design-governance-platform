from datetime import UTC, datetime

from fastapi import FastAPI, Header, HTTPException

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIModelConfig
from app.ai_service import ModelRequest, validate_requirement_analysis_output
from app.main_route_context import AppRouteContext
from app.project_asset_api import require_project
from app.requirement_repository import RequirementRepository
from app.requirement_schemas import RequirementVersion
from app.review_repository import RequirementReviewRepository
from app.review_schemas import (
    AtomicRequirementUpdate,
    FindingUpdate,
    RequirementAnalysis,
    RequirementAnalysisInput,
    RequirementConfirmationInput,
    RequirementConflict,
    RequirementConflictDecisionInput,
    RequirementSelectionInput,
    VisualInferenceUpdate,
)
from app.review_service import build_analysis_candidates, semantic_output_to_analysis, source_reference_exists
from app.repository import ProjectRepository


def require_review(
    repository: ProjectRepository,
    review_repository: RequirementReviewRepository,
    project_id: int,
    analysis_id: int,
) -> RequirementAnalysis:
    """保留需求评审不存在时的统一错误语义。"""
    require_project(repository.get(project_id))
    analysis = review_repository.get(project_id, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="需求评审不存在")
    return analysis


def register_requirement_review_routes(app: FastAPI, context: AppRouteContext) -> None:
    """注册需求评审、编辑、冲突和确认接口。"""
    repository = context.repository
    requirement_repository: RequirementRepository = context.requirement_repository
    review_repository: RequirementReviewRepository = context.review_repository
    ai_run_repository: AIRunRepository = context.ai_run_repository

    @app.post(
        "/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review",
        response_model=RequirementAnalysis,
        status_code=201,
    )
    def create_requirement_review(
        project_id: int,
        version_id: int,
        analysis_input: RequirementAnalysisInput | None = None,
        x_session_id: str | None = Header(default=None),
    ) -> RequirementAnalysis:
        require_project(repository.get(project_id))
        version = requirement_repository.get_version(project_id, version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="需求版本不存在")
        existing = review_repository.latest_for_version(project_id, version_id)
        if existing is not None:
            return existing
        analysis_input = analysis_input or RequirementAnalysisInput()
        input_asset_versions = [
            {"asset_id": material.asset_id, "revision": material.asset_revision}
            for material in version.materials
        ]
        context_values = tuple(
            {"text": fragment.text, "source_reference": fragment.source_reference.model_dump(mode="json")}
            for material in version.materials for fragment in material.fragments
        )
        from app.model_config_api import get_session_model_config

        session_config = get_session_model_config(x_session_id) if analysis_input.mode == "real" else None
        if analysis_input.mode == "real" and session_config is None:
            raise HTTPException(status_code=422, detail="未配置真实模型；请先保存当前会话模型配置")
        model_parameters = AIModelConfig(
            provider=session_config.provider if session_config else "mock",
            model=session_config.model if session_config else "deterministic-v1",
        )
        request = ModelRequest(
            task_type="requirement_review",
            prompt_version="requirement-analysis.v1",
            model_parameters=model_parameters,
            input_asset_versions=tuple(input_asset_versions),
            scenario=analysis_input.scenario,
            input_context=context_values,
            base_url=session_config.base_url if session_config else "",
            api_key=session_config.api_key if session_config else "",
        )
        selected_model_service = context.real_model_service if analysis_input.mode == "real" else context.model_service
        attempts: list[AIAttempt] = []
        output = None
        validation_errors: list[str] = []
        run_status = "failed"
        validation_status = "not_run"
        for attempt_number in range(1, analysis_input.max_retries + 2):
            started_at = datetime.now(UTC)
            response = selected_model_service.complete(request)
            elapsed_ms = max(0, int((datetime.now(UTC) - started_at).total_seconds() * 1000))
            if response.error_code:
                attempts.append(AIAttempt(
                    attempt=attempt_number,
                    started_at=started_at,
                    elapsed_ms=elapsed_ms,
                    status="failed",
                    error_code=response.error_code,
                    retryable=response.retryable,
                ))
                if not response.retryable or attempt_number == analysis_input.max_retries + 1:
                    break
                continue
            output, validation_errors = validate_requirement_analysis_output(response.raw_output)
            if validation_errors:
                attempts.append(AIAttempt(
                    attempt=attempt_number,
                    started_at=started_at,
                    elapsed_ms=elapsed_ms,
                    status="validation_failed",
                    error_code="schema_invalid",
                    retryable=False,
                ))
                validation_status = "failed"
                run_status = "validation_failed"
                break
            validation_status = "passed"
            run_status = "succeeded"
            attempts.append(AIAttempt(
                attempt=attempt_number,
                started_at=started_at,
                elapsed_ms=elapsed_ms,
                status="succeeded",
                error_code=None,
                retryable=False,
            ))
            break
        if output is None:
            raise HTTPException(status_code=502 if run_status == "failed" else 422,
                                detail=validation_errors or "模型分析失败")
        requirements, test_items, criteria, atomic_requirements, findings, conflicts = (
            semantic_output_to_analysis(version, output)
        )
        _, _, visual_inferences = build_analysis_candidates(version)
        from app.ai_schemas import AIRun

        ai_run = ai_run_repository.create_run(
            AIRun(
                id=0,
                project_id=project_id,
                task_type="requirement_review",
                model_parameters=model_parameters,
                prompt_version="requirement-analysis.v1",
                input_asset_versions=input_asset_versions,
                output=output.model_dump(mode="json"),
                validation_status=validation_status,
                validation_errors=validation_errors,
                status=run_status,
                is_mock=analysis_input.mode == "mock",
                created_at=datetime.now(UTC),
                attempts=attempts,
            )
        )
        analysis = RequirementAnalysis(
            id=0,
            project_id=project_id,
            requirement_version_id=version_id,
            atomic_requirements=atomic_requirements,
            findings=findings,
            visual_inferences=visual_inferences,
            requirements=requirements,
            conflicts=conflicts,
            selected_requirement_ids=[item.requirement_id for item in requirements],
            test_items=test_items,
            acceptance_criteria=criteria,
            is_mock=analysis_input.mode == "mock",
            ai_run_id=ai_run.id,
        )
        return review_repository.create(analysis)

    @app.get("/api/projects/{project_id}/requirement-reviews/{analysis_id}", response_model=RequirementAnalysis)
    def get_requirement_review(project_id: int, analysis_id: int) -> RequirementAnalysis:
        require_project(repository.get(project_id))
        analysis = review_repository.get(project_id, analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="需求评审不存在")
        return analysis

    @app.get("/api/projects/{project_id}/requirement-reviews/{analysis_id}/history")
    def get_requirement_review_history(project_id: int, analysis_id: int) -> list[dict]:
        require_project(repository.get(project_id))
        history = review_repository.history(project_id, analysis_id)
        if history is None:
            raise HTTPException(status_code=404, detail="需求评审不存在")
        return history

    @app.patch(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/atomic-requirements/{candidate_id}",
        response_model=RequirementAnalysis,
    )
    def update_atomic_requirement(
        project_id: int, analysis_id: int, candidate_id: str, update: AtomicRequirementUpdate
    ) -> RequirementAnalysis:
        analysis = require_review(repository, review_repository, project_id, analysis_id)
        candidate = next((item for item in analysis.atomic_requirements if item.candidate_id == candidate_id), None)
        if candidate is None:
            raise HTTPException(status_code=404, detail="原子需求候选不存在")
        if analysis.status == "confirmed":
            raise HTTPException(status_code=409, detail="需求确认后不能修改原子需求")
        now = datetime.now(UTC)
        version = requirement_repository.get_version(project_id, analysis.requirement_version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="需求版本不存在")
        if update.source_reference is not None and not source_reference_exists(version, update.source_reference):
            raise HTTPException(status_code=422, detail="原子需求来源引用不存在")
        if update.statement is not None:
            candidate.statement = update.statement
        if update.source_reference is not None:
            candidate.source_reference = update.source_reference
        if update.decision is not None:
            candidate.decision = update.decision
            if update.decision == "accepted" and candidate.stable_requirement_id is None:
                candidate.stable_requirement_id = f"REQ-{candidate.candidate_id.removeprefix('candidate-')}"
        if update.split_into:
            candidate.decision = "rejected"
            for index, statement in enumerate(update.split_into, start=1):
                analysis.atomic_requirements.append(candidate.model_copy(update={
                    "candidate_id": f"{candidate.candidate_id}-split-{index}",
                    "stable_requirement_id": None,
                    "statement": statement,
                    "decision": "pending_confirmation",
                    "created_at": now,
                    "updated_at": now,
                }))
        if update.merge_candidate_ids:
            merge_ids = {candidate_id, *update.merge_candidate_ids}
            merge_candidates = [item for item in analysis.atomic_requirements if item.candidate_id in merge_ids]
            if len(merge_candidates) != len(merge_ids):
                raise HTTPException(status_code=422, detail="合并目标中包含不存在的原子需求候选")
            candidate.statement = "；".join(item.statement for item in merge_candidates)
            candidate.decision = "pending_confirmation"
            candidate.stable_requirement_id = None
            for item in merge_candidates:
                if item.candidate_id != candidate_id:
                    item.decision = "rejected"
                    item.updated_at = now
        candidate.updated_at = now
        return review_repository.save(analysis, "atomic_requirement_updated")

    @app.patch(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/findings/{finding_id}",
        response_model=RequirementAnalysis,
    )
    def update_review_finding(
        project_id: int, analysis_id: int, finding_id: str, update: FindingUpdate
    ) -> RequirementAnalysis:
        analysis = require_review(repository, review_repository, project_id, analysis_id)
        finding = next((item for item in analysis.findings if item.finding_id == finding_id), None)
        if finding is None:
            raise HTTPException(status_code=404, detail="需求评审发现不存在")
        if analysis.status == "confirmed":
            raise HTTPException(status_code=409, detail="需求确认后不能修改评审发现")
        finding.status = update.status
        if update.reason is not None:
            finding.reason = update.reason
        finding.updated_at = datetime.now(UTC)
        return review_repository.save(analysis, "review_finding_updated")

    @app.patch(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/visual-inferences/{inference_id}",
        response_model=RequirementAnalysis,
    )
    def update_visual_inference(
        project_id: int, analysis_id: int, inference_id: str, update: VisualInferenceUpdate
    ) -> RequirementAnalysis:
        analysis = require_review(repository, review_repository, project_id, analysis_id)
        inference = next((item for item in analysis.visual_inferences if item.inference_id == inference_id), None)
        if inference is None:
            raise HTTPException(status_code=404, detail="视觉推断不存在")
        if analysis.status == "confirmed":
            raise HTTPException(status_code=409, detail="需求确认后不能修改视觉推断")
        inference.decision = update.decision
        inference.updated_at = datetime.now(UTC)
        return review_repository.save(analysis, "visual_inference_updated")

    @app.patch(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/selection",
        response_model=RequirementAnalysis,
    )
    def update_requirement_selection(
        project_id: int, analysis_id: int, selection: RequirementSelectionInput
    ) -> RequirementAnalysis:
        analysis = require_review(repository, review_repository, project_id, analysis_id)
        if analysis.status == "confirmed":
            raise HTTPException(status_code=409, detail="需求确认后不能修改需求表选择")
        known_ids = {item.requirement_id for item in analysis.requirements}
        if any(item not in known_ids for item in selection.selected_requirement_ids):
            raise HTTPException(status_code=422, detail="需求表包含未知需求")
        analysis.selected_requirement_ids = list(dict.fromkeys(selection.selected_requirement_ids))
        return review_repository.save(analysis, "requirement_selection_updated")

    @app.get(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/conflicts",
        response_model=list[RequirementConflict],
    )
    def list_requirement_conflicts(project_id: int, analysis_id: int) -> list[RequirementConflict]:
        analysis = require_review(repository, review_repository, project_id, analysis_id)
        return analysis.conflicts

    @app.patch(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/conflicts/{conflict_id}",
        response_model=RequirementAnalysis,
    )
    def decide_requirement_conflict(
        project_id: int, analysis_id: int, conflict_id: str, decision: RequirementConflictDecisionInput
    ) -> RequirementAnalysis:
        analysis = require_review(repository, review_repository, project_id, analysis_id)
        if analysis.status == "confirmed":
            raise HTTPException(status_code=409, detail="需求确认后不能修改冲突处理")
        conflict = next((item for item in analysis.conflicts if item.conflict_id == conflict_id), None)
        if conflict is None:
            raise HTTPException(status_code=404, detail="需求冲突不存在")
        conflict.decision = decision.decision
        conflict.decided_by = decision.confirmer_name
        conflict.decision_note = decision.decision_note
        return review_repository.save(analysis, "requirement_conflict_decided")

    @app.post(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/confirm",
        response_model=RequirementAnalysis,
    )
    def confirm_requirement_review(
        project_id: int, analysis_id: int, confirmation: RequirementConfirmationInput
    ) -> RequirementAnalysis:
        analysis = require_review(repository, review_repository, project_id, analysis_id)
        if analysis.status == "confirmed":
            raise HTTPException(status_code=409, detail="需求确认已经完成")
        if any(item.decision == "pending_confirmation" for item in analysis.atomic_requirements):
            raise HTTPException(status_code=409, detail="仍有原子需求候选待确认")
        if any(item.status == "pending_confirmation" for item in analysis.findings):
            raise HTTPException(status_code=409, detail="仍有需求评审发现待处置")
        if any(item.decision == "pending_confirmation" for item in analysis.visual_inferences):
            raise HTTPException(status_code=409, detail="仍有视觉推断待确认")
        unresolved_modules = {
            module for item in analysis.conflicts
            if item.decision in {"unresolved", "awaiting_external_confirmation"}
            for module in item.affected_modules
        }
        selected_modules = {
            item.module for item in analysis.requirements
            if item.requirement_id in analysis.selected_requirement_ids
        }
        if unresolved_modules.intersection(selected_modules):
            raise HTTPException(status_code=409, detail="请先处理已选择需求所属模块的冲突")
        analysis.status = "confirmed"
        analysis.confirmed_by = confirmation.confirmer_name
        analysis.confirmed_at = datetime.now(UTC)
        return review_repository.save(analysis, "requirement_confirmed")
