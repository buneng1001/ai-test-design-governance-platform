from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, status

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIRun, AIModelConfig
from app.ai_service import validate_output
from app.design_repository import DesignRepository
from app.design_schemas import (
    AutomationCandidate,
    AutomationFactors,
    AutomationInput,
    DesignAsset,
    DesignConfirmationInput,
    DesignCreateInput,
    DimensionInput,
    DimensionMergeInput,
    DimensionUpdate,
    RiskAssessment,
    RiskFactor,
    RiskInput,
    TestDimension,
    TestScopeItem,
    ScopeItemInput,
)
from app.design_service import automation_reason, calculate_automation, calculate_risk, priority_for, stable_id
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.review_repository import RequirementReviewRepository
from app.review_schemas import RequirementAnalysis


def register_design_routes(
    app: FastAPI,
    repository: ProjectRepository,
    requirement_repository: RequirementRepository,
    review_repository: RequirementReviewRepository,
    design_repository: DesignRepository,
    ai_run_repository: AIRunRepository,
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/requirement-versions/{version_id}/test-designs",
        response_model=DesignAsset,
        status_code=status.HTTP_201_CREATED,
    )
    def create_design(project_id: int, version_id: int, input_data: DesignCreateInput) -> DesignAsset:
        _require_project(repository, project_id)
        version = requirement_repository.get_version(project_id, version_id)
        review = review_repository.latest_for_version(project_id, version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="需求版本不存在")
        if review is None or review.status != "confirmed":
            raise HTTPException(status_code=409, detail="需求确认后才能建立测试设计")
        existing = design_repository.latest_for_version(project_id, version_id)
        if existing is not None:
            return existing
        dimensions = [
            TestDimension(id=stable_id("dimension", name), name=name, sort_order=index)
            for index, name in enumerate(input_data.dimension_names)
        ]
        scope_items = _scopes(review, dimensions[0].id)
        raw_ai_output = {
            "contract_version": "ai-output.v1",
            "items": [
                {
                    "candidate_id": item.id,
                    "summary": item.title,
                    "source_asset_ids": [material.asset_id for material in version.materials],
                }
                for item in scope_items
            ],
        }
        ai_output, validation_errors = validate_output(raw_ai_output)
        if validation_errors:
            raise HTTPException(status_code=500, detail="测试设计 AI 输出校验失败")
        ai_run = ai_run_repository.create_run(AIRun(
            id=0,
            project_id=project_id,
            task_type="scope_analysis",
            model_parameters=AIModelConfig(),
            prompt_version="design.v1",
            input_asset_versions=[
                {"asset_id": material.asset_id, "revision": material.asset_revision}
                for material in version.materials
            ],
            output=ai_output,
            validation_status="passed" if ai_output is not None else "failed",
            validation_errors=validation_errors,
            status="succeeded",
            is_mock=True,
            created_at=datetime.now(UTC),
            attempts=[AIAttempt(attempt=1, started_at=datetime.now(UTC), elapsed_ms=0, status="succeeded")],
        ))
        design = DesignAsset(
            id=0,
            project_id=project_id,
            requirement_version_id=version_id,
            dimensions=dimensions,
            scope_items=scope_items,
            risks=[_default_risk(item, review) for item in scope_items],
            automation_candidates=[_default_automation(item.id) for item in scope_items],
            ai_run_id=ai_run.id,
        )
        return design_repository.create(design)

    @router.get("/api/projects/{project_id}/test-designs/{design_id}", response_model=DesignAsset)
    def get_design(project_id: int, design_id: int) -> DesignAsset:
        _require_project(repository, project_id)
        design = design_repository.get(project_id, design_id)
        if design is None:
            raise HTTPException(status_code=404, detail="测试设计不存在")
        return design

    @router.get("/api/projects/{project_id}/test-designs/{design_id}/history")
    def get_history(project_id: int, design_id: int) -> list[dict]:
        _require_project(repository, project_id)
        history = design_repository.history(project_id, design_id)
        if history is None:
            raise HTTPException(status_code=404, detail="测试设计不存在")
        return history

    @router.post("/api/projects/{project_id}/test-designs/{design_id}/dimensions", response_model=DesignAsset)
    def add_dimension(project_id: int, design_id: int, data: DimensionInput) -> DesignAsset:
        design = _draft(repository, design_repository, project_id, design_id)
        if data.parent_id and not _dimension(design, data.parent_id):
            raise HTTPException(status_code=422, detail="父项目测试维度不存在")
        dimension = TestDimension(id=stable_id("dimension", f"{design_id}:{data.name}"), **data.model_dump())
        if any(item.name == dimension.name and item.status == "active" for item in design.dimensions):
            raise HTTPException(status_code=409, detail="项目测试维度名称已经存在")
        design.dimensions.append(dimension)
        return design_repository.save(design, "dimension_added")

    @router.patch(
        "/api/projects/{project_id}/test-designs/{design_id}/dimensions/{dimension_id}",
        response_model=DesignAsset,
    )
    def update_dimension(
        project_id: int, design_id: int, dimension_id: str, data: DimensionUpdate
    ) -> DesignAsset:
        design = _draft(repository, design_repository, project_id, design_id)
        dimension = _require_dimension(design, dimension_id)
        if data.parent_id == dimension_id or (data.parent_id and not _dimension(design, data.parent_id)):
            raise HTTPException(status_code=422, detail="项目测试维度父子关系无效")
        dimension.name, dimension.parent_id = data.name, data.parent_id
        dimension.sort_order, dimension.status = data.sort_order, data.status
        return design_repository.save(design, "dimension_updated")

    @router.delete(
        "/api/projects/{project_id}/test-designs/{design_id}/dimensions/{dimension_id}",
        response_model=DesignAsset,
    )
    def deactivate_dimension(
        project_id: int, design_id: int, dimension_id: str
    ) -> DesignAsset:
        design = _draft(repository, design_repository, project_id, design_id)
        dimension = _require_dimension(design, dimension_id)
        if any(item.primary_dimension_id == dimension_id for item in design.scope_items):
            raise HTTPException(status_code=409, detail="已被资产引用的项目测试维度不能直接删除")
        dimension.status = "inactive"
        return design_repository.save(design, "dimension_deactivated")

    @router.post(
        "/api/projects/{project_id}/test-designs/{design_id}/dimensions/{dimension_id}/merge",
        response_model=DesignAsset,
    )
    def merge_dimension(
        project_id: int, design_id: int, dimension_id: str, data: DimensionMergeInput
    ) -> DesignAsset:
        design = _draft(repository, design_repository, project_id, design_id)
        source = _require_dimension(design, dimension_id)
        target = _require_dimension(design, data.target_dimension_id)
        if source.id == target.id:
            raise HTTPException(status_code=422, detail="项目测试维度不能合并到自身")
        for item in design.scope_items:
            if item.primary_dimension_id == source.id:
                item.primary_dimension_id = target.id
            item.secondary_dimension_ids = [
                target.id if value == source.id else value for value in item.secondary_dimension_ids
            ]
        source.status = "inactive"
        return design_repository.save(design, "dimension_merged")

    @router.post("/api/projects/{project_id}/test-designs/{design_id}/scope-items", response_model=DesignAsset)
    def add_scope(
        project_id: int, design_id: int, data: ScopeItemInput
    ) -> DesignAsset:
        design = _draft(repository, design_repository, project_id, design_id)
        valid = {item.id for item in design.dimensions if item.status == "active"}
        if data.primary_dimension_id not in valid or not set(data.secondary_dimension_ids) <= valid:
            raise HTTPException(status_code=422, detail="测试范围项只能关联有效的项目测试维度")
        design.scope_items.append(
            TestScopeItem(id=stable_id("scope", f"{design_id}:{data.title}"), **data.model_dump())
        )
        return design_repository.save(design, "scope_item_added")

    @router.patch(
        "/api/projects/{project_id}/test-designs/{design_id}/risks/{scope_item_id}",
        response_model=DesignAsset,
    )
    def update_risk(
        project_id: int, design_id: int, scope_item_id: str, data: RiskInput
    ) -> DesignAsset:
        design = _draft(repository, design_repository, project_id, design_id)
        if data.adjustment_reason is None:
            raise HTTPException(status_code=422, detail="人工调整风险因子必须记录理由")
        if any(not factor.source_references for factor in data.factors):
            raise HTTPException(status_code=422, detail="风险因子必须保留需求来源引用")
        scope = _require_scope(design, scope_item_id)
        score, level = calculate_risk(data.factors)
        risk = RiskAssessment(
            scope_item_id=scope.id, factors=data.factors, final_score=score, risk_level=level,
            priority=priority_for(
                score, scope.business_criticality, scope.requirement_change_level,
                scope.historical_failure_count,
            ),
            adjustment_reason=data.adjustment_reason,
        )
        design.risks = [item for item in design.risks if item.scope_item_id != scope_item_id] + [risk]
        return design_repository.save(design, "risk_adjusted")

    @router.patch(
        "/api/projects/{project_id}/test-designs/{design_id}/automation/{scope_item_id}",
        response_model=DesignAsset,
    )
    def update_automation(
        project_id: int, design_id: int, scope_item_id: str, data: AutomationInput
    ) -> DesignAsset:
        design = _draft(repository, design_repository, project_id, design_id)
        _require_scope(design, scope_item_id)
        candidate = AutomationCandidate(
            scope_item_id=scope_item_id, factors=data.factors,
            suggested_score=calculate_automation(data.factors), suggestion_reason=automation_reason(data.factors),
            decision=data.decision, decision_reason=data.decision_reason,
        )
        design.automation_candidates = [
            item for item in design.automation_candidates if item.scope_item_id != scope_item_id
        ]
        design.automation_candidates.append(candidate)
        return design_repository.save(design, "automation_decision_updated")

    @router.post("/api/projects/{project_id}/test-designs/{design_id}/confirm", response_model=DesignAsset)
    def confirm_design(project_id: int, design_id: int, data: DesignConfirmationInput) -> DesignAsset:
        design = _draft(repository, design_repository, project_id, design_id)
        ids = {item.id for item in design.scope_items}
        if (
            not ids
            or {item.scope_item_id for item in design.risks} != ids
            or {item.scope_item_id for item in design.automation_candidates} != ids
        ):
            raise HTTPException(status_code=409, detail="每个测试范围项都必须完成风险和自动化决定")
        design.status, design.confirmed_by, design.confirmed_at = "confirmed", data.confirmer_name, datetime.now(UTC)
        return design_repository.save(design, "design_confirmed")

    app.include_router(router)


def _require_project(repository: ProjectRepository, project_id: int) -> None:
    if repository.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")


def _draft(
    repository: ProjectRepository, designs: DesignRepository, project_id: int, design_id: int
) -> DesignAsset:
    _require_project(repository, project_id)
    design = designs.get(project_id, design_id)
    if design is None:
        raise HTTPException(status_code=404, detail="测试设计不存在")
    if design.status == "confirmed":
        raise HTTPException(status_code=409, detail="设计确认后不能修改测试设计")
    return design


def _dimension(design: DesignAsset, dimension_id: str) -> TestDimension | None:
    return next((item for item in design.dimensions if item.id == dimension_id), None)


def _require_dimension(design: DesignAsset, dimension_id: str) -> TestDimension:
    dimension = _dimension(design, dimension_id)
    if dimension is None:
        raise HTTPException(status_code=404, detail="项目测试维度不存在")
    return dimension


def _require_scope(design: DesignAsset, scope_id: str) -> TestScopeItem:
    scope = next((item for item in design.scope_items if item.id == scope_id), None)
    if scope is None:
        raise HTTPException(status_code=404, detail="测试范围项不存在")
    return scope


def _scopes(review: RequirementAnalysis, dimension_id: str) -> list[TestScopeItem]:
    return [
        TestScopeItem(
            id=stable_id("scope", item.stable_requirement_id or item.candidate_id), title=item.statement[:200],
            description=item.statement, requirement_ids=[item.stable_requirement_id or item.candidate_id],
            primary_dimension_id=dimension_id,
        )
        for item in review.atomic_requirements if item.decision == "accepted"
    ]


def _default_risk(scope: TestScopeItem, review: RequirementAnalysis) -> RiskAssessment:
    reference = next(
        (
            item.source_reference
            for item in review.atomic_requirements
            if item.stable_requirement_id in scope.requirement_ids
        ),
        None,
    )
    factor = RiskFactor(
        key="business_impact", name="业务影响", score=scope.business_criticality, weight=1,
        suggested_score=scope.business_criticality,
        suggestion_reason="根据已确认原子需求生成候选分，仍需测试工程师确认。",
        source_references=[reference] if reference else [],
    )
    score, level = calculate_risk([factor])
    return RiskAssessment(
        scope_item_id=scope.id, factors=[factor], final_score=score, risk_level=level,
        priority=priority_for(
            score, scope.business_criticality, scope.requirement_change_level,
            scope.historical_failure_count,
        ),
    )


def _default_automation(scope_id: str) -> AutomationCandidate:
    factors = AutomationFactors(
        regression_value=3, determinism=3, environment_control=3, saving_benefit=3,
        maintenance_cost=3, manual_observation=3,
    )
    return AutomationCandidate(
        scope_item_id=scope_id, factors=factors, suggested_score=calculate_automation(factors),
        suggestion_reason=automation_reason(factors),
    )
