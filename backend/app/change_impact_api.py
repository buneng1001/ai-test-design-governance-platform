from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, status

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIModelConfig, AIRun
from app.case_review_repository import CaseReviewRepository
from app.change_impact_repository import ChangeImpactRepository
from app.change_impact_data import batches_for_project, case_reviews_for_project, designs_for_project
from app.change_impact_regression import build_regression_candidates
from app.change_impact_schemas import (
    ChangeConfirmationInput,
    ChangeImpactAnalysis,
    ChangeImpactInput,
    ImpactLink,
    RegressionCandidate,
    RegressionConfirmationInput,
    RegressionSelection,
    RequirementChange,
)
from app.design_repository import DesignRepository
from app.execution_batch_repository import ExecutionBatchRepository
from app.execution_result_repository import ExecutionResultRepository
from app.quality_repository import QualityRepository
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.review_repository import RequirementReviewRepository
from app.task_repository import TestTaskRepository


def register_change_impact_routes(
    app: FastAPI,
    projects: ProjectRepository,
    requirements: RequirementRepository,
    reviews: RequirementReviewRepository,
    designs: DesignRepository,
    case_reviews: CaseReviewRepository,
    batches: ExecutionBatchRepository,
    results: ExecutionResultRepository,
    quality: QualityRepository,
    tasks: TestTaskRepository,
    ai_runs: AIRunRepository,
    repository: ChangeImpactRepository,
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/change-impact-analyses",
        response_model=ChangeImpactAnalysis,
        status_code=status.HTTP_201_CREATED,
    )
    def create_analysis(project_id: int, data: ChangeImpactInput) -> ChangeImpactAnalysis:
        _require_project(projects, project_id)
        if data.base_version_id == data.target_version_id:
            raise HTTPException(status_code=422, detail="变更影响必须比较两个不同的需求版本")
        base = requirements.get_version(project_id, data.base_version_id)
        target = requirements.get_version(project_id, data.target_version_id)
        base_review = reviews.latest_for_version(project_id, data.base_version_id)
        target_review = reviews.latest_for_version(project_id, data.target_version_id)
        if not base or not target or not base_review or not target_review:
            raise HTTPException(status_code=409, detail="两个需求版本及其需求评审必须先完成")
        if base_review.status != "confirmed" or target_review.status != "confirmed":
            raise HTTPException(status_code=409, detail="两个需求版本必须先完成需求确认")
        changes = _compare_requirements(base_review.atomic_requirements, target_review.atomic_requirements)
        now = datetime.now(UTC)
        ai_run = ai_runs.create_run(AIRun(
            id=0, project_id=project_id, task_type="change_impact_analysis", model_parameters=AIModelConfig(),
            prompt_version="change-impact.v1", input_asset_versions=[
                {"version_id": data.base_version_id}, {"version_id": data.target_version_id}
            ], output={"contract_version": "ai-output.v1", "change_ids": [item.id for item in changes]},
            validation_status="passed", validation_errors=[], status="succeeded", is_mock=True, created_at=now,
            attempts=[AIAttempt(attempt=1, started_at=now, elapsed_ms=0, status="succeeded")],
        ))
        analysis = ChangeImpactAnalysis(
            id=0, project_id=project_id, base_version_id=data.base_version_id, target_version_id=data.target_version_id,
            changes=changes, created_at=now,
        )
        return repository.create_analysis(analysis)

    @router.post(
        "/api/projects/{project_id}/requirement-versions/{target_version_id}/change-impact",
        response_model=ChangeImpactAnalysis,
        status_code=status.HTTP_201_CREATED,
    )
    def create_analysis_alias(project_id: int, target_version_id: int, data: ChangeImpactInput) -> ChangeImpactAnalysis:
        return create_analysis(project_id, data.model_copy(update={"target_version_id": target_version_id}))

    @router.get("/api/projects/{project_id}/change-impact-analyses/{analysis_id}", response_model=ChangeImpactAnalysis)
    def get_analysis(project_id: int, analysis_id: int) -> ChangeImpactAnalysis:
        _require_project(projects, project_id)
        analysis = repository.get_analysis(project_id, analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="变更影响分析不存在")
        return analysis

    @router.post(
        "/api/projects/{project_id}/change-impact-analyses/{analysis_id}/confirm",
        response_model=ChangeImpactAnalysis,
    )
    def confirm_changes(project_id: int, analysis_id: int, data: ChangeConfirmationInput) -> ChangeImpactAnalysis:
        _require_project(projects, project_id)
        analysis = _get_analysis(repository, project_id, analysis_id)
        if analysis.status != "pending_change_confirmation":
            raise HTTPException(status_code=409, detail="需求变更已经完成确认")
        if set(data.decisions) != {item.id for item in analysis.changes}:
            raise HTTPException(status_code=422, detail="必须逐项确认全部需求变更")
        now = datetime.now(UTC)
        for item in analysis.changes:
            item.status = data.decisions[item.id]
            item.confirmed_by = data.confirmer_name
            item.confirmed_at = now
        confirmed_ids = {item.id for item in analysis.changes if item.status == "confirmed"}
        analysis.status = "confirmed"
        analysis.confirmed_by, analysis.confirmed_at = data.confirmer_name, now
        analysis.impacts = _build_impacts(project_id, analysis, confirmed_ids, designs, case_reviews, tasks)
        _mark_affected_cases(project_id, analysis, case_reviews)
        analysis.regression_candidates, analysis.ai_supplements = build_regression_candidates(
            project_id, analysis, designs, case_reviews, batches, results, quality, tasks
        )
        return repository.save_analysis(analysis, "changes_confirmed")

    @router.post(
        "/api/projects/{project_id}/change-impact-analyses/{analysis_id}/regression-selection",
        response_model=RegressionSelection,
        status_code=status.HTTP_201_CREATED,
    )
    def create_selection(project_id: int, analysis_id: int) -> RegressionSelection:
        _require_project(projects, project_id)
        analysis = _get_analysis(repository, project_id, analysis_id)
        if analysis.status != "confirmed":
            raise HTTPException(status_code=409, detail="必须先确认需求变更")
        selection = RegressionSelection(
            id=0, project_id=project_id, analysis_id=analysis_id,
            candidates=[*analysis.regression_candidates, *analysis.ai_supplements],
            created_at=datetime.now(UTC),
        )
        return repository.create_selection(selection)

    @router.get("/api/projects/{project_id}/regression-selections/{selection_id}", response_model=RegressionSelection)
    def get_selection(project_id: int, selection_id: int) -> RegressionSelection:
        _require_project(projects, project_id)
        selection = repository.get_selection(project_id, selection_id)
        if selection is None:
            raise HTTPException(status_code=404, detail="回归选择不存在")
        return selection

    @router.post(
        "/api/projects/{project_id}/regression-selections/{selection_id}/confirm",
        response_model=RegressionSelection,
    )
    def confirm_selection(project_id: int, selection_id: int,
                          data: RegressionConfirmationInput) -> RegressionSelection:
        _require_project(projects, project_id)
        selection = repository.get_selection(project_id, selection_id)
        if selection is None:
            raise HTTPException(status_code=404, detail="回归选择不存在")
        if selection.status != "pending_confirmation":
            raise HTTPException(status_code=409, detail="回归选择已经完成确认")
        candidates = {item.stable_case_id: item for item in selection.candidates}
        if set(data.decisions) != set(candidates):
            raise HTTPException(status_code=422, detail="必须逐项确认全部回归候选")
        for case_id, selected in data.decisions.items():
            candidates[case_id].selected = selected
            candidates[case_id].decision_reason = data.reasons.get(case_id)
        selection.status = "confirmed"
        selection.confirmed_by, selection.confirmed_at = data.confirmer_name, datetime.now(UTC)
        return repository.save_selection(selection)

    app.include_router(router)


def _compare_requirements(base_items, target_items) -> list[RequirementChange]:
    base = {item.stable_requirement_id: item for item in base_items if item.decision == "accepted"}
    target = {item.stable_requirement_id: item for item in target_items if item.decision == "accepted"}
    base_by_locator = {item.source_reference.locator: item for item in base.values()}
    matched_target_ids: set[str] = set()
    changes: list[RequirementChange] = []
    for requirement_id, item in target.items():
        previous = base.get(requirement_id) or base_by_locator.get(item.source_reference.locator)
        stable_id = previous.stable_requirement_id if previous else requirement_id
        matched_target_ids.add(requirement_id)
        if previous is None:
            changes.append(RequirementChange(
                id=f"change-{item.candidate_id}", change_type="added", summary=f"新增需求：{item.statement}",
                target_requirement_id=stable_id, target_source_reference=item.source_reference,
            ))
        elif previous.statement != item.statement:
            changes.append(RequirementChange(
                id=f"change-{stable_id}", change_type="modified", summary=f"需求内容发生修改：{item.statement}",
                base_requirement_id=stable_id, target_requirement_id=stable_id,
                base_source_reference=previous.source_reference,
                target_source_reference=item.source_reference,
            ))
        else:
            changes.append(RequirementChange(
                id=f"change-{stable_id}", change_type="suspected_continuation", summary="需求疑似延续，来源引用保持可追踪",
                base_requirement_id=stable_id, target_requirement_id=stable_id,
                base_source_reference=previous.source_reference,
                target_source_reference=item.source_reference,
            ))
    for requirement_id, item in base.items():
        if requirement_id not in {item.stable_requirement_id for item in target.values()} and not any(
            target_item.source_reference.locator == item.source_reference.locator for target_item in target.values()
        ):
            changes.append(RequirementChange(
                id=f"change-deleted-{requirement_id}", change_type="deleted", summary=f"删除需求：{item.statement}",
                base_requirement_id=requirement_id, base_source_reference=item.source_reference,
            ))
    return changes


def _build_impacts(project_id: int, analysis: ChangeImpactAnalysis, confirmed_ids: set[str], designs,
                   case_reviews, tasks) -> list[ImpactLink]:
    changed_requirements = {
        item.target_requirement_id or item.base_requirement_id for item in analysis.changes if item.id in confirmed_ids
    }
    links: list[ImpactLink] = []
    for design in designs_for_project(designs, project_id):
        for scope in design.scope_items:
            matched = set(scope.requirement_ids) & changed_requirements
            if matched:
                links.append(ImpactLink(kind="scope", identifier=scope.id, title=scope.title,
                                        change_ids=[
                                            item.id for item in analysis.changes
                                            if (item.target_requirement_id or item.base_requirement_id) in matched
                                        ],
                                        reason="测试范围项追踪到已确认需求变更"))
                risk = next((item for item in design.risks if item.scope_item_id == scope.id), None)
                if risk:
                    links.append(ImpactLink(kind="risk", identifier=risk.scope_item_id, title=risk.risk_level,
                                            change_ids=[
                                                item.id for item in analysis.changes
                                                if (item.target_requirement_id or item.base_requirement_id) in matched
                                            ],
                                            reason="风险项沿测试范围项追踪受影响"))
    for batch in case_reviews_for_project(case_reviews, project_id):
        for revision in batch.revisions:
            matched = set(revision.candidate.requirement_ids) & changed_requirements
            if matched and revision.stable_case_id:
                links.append(ImpactLink(kind="case", identifier=revision.stable_case_id, title=revision.candidate.title,
                                        change_ids=[
                                            item.id for item in analysis.changes
                                            if (item.target_requirement_id or item.base_requirement_id) in matched
                                        ],
                                        reason="测试用例追踪到受影响原子需求"))
    for task in tasks.list_for_project(project_id):
        affected = {item.identifier for item in links if item.kind == "case"} & {
            case.stable_case_id for case in task.cases
        }
        if affected:
            links.append(ImpactLink(kind="task", identifier=task.task_id, title=task.task_id,
                                    change_ids=list(confirmed_ids), reason="测试任务包含受影响测试用例"))
    return links


def _mark_affected_cases(project_id: int, analysis: ChangeImpactAnalysis, case_reviews) -> None:
    changed = {
        item.target_requirement_id or item.base_requirement_id
        for item in analysis.changes if item.status == "confirmed"
    }
    for batch in case_reviews_for_project(case_reviews, project_id):
        touched = False
        for revision in batch.revisions:
            if revision.stable_case_id and set(revision.candidate.requirement_ids) & changed:
                revision.participation_status = "pending_impact"
                touched = True
        if touched:
            case_reviews.save(batch, "change_impact_pending")


def _get_analysis(repository: ChangeImpactRepository, project_id: int, analysis_id: int) -> ChangeImpactAnalysis:
    analysis = repository.get_analysis(project_id, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="变更影响分析不存在")
    return analysis


def _require_project(projects: ProjectRepository, project_id: int) -> None:
    if projects.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")
