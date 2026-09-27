from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, Header, HTTPException, status

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIRun, AIModelConfig
from app.ai_service import ModelRequest, MockModelService, OpenAICompatibleModelService
from app.case_generation_contract import validate_case_generation_output
from app.model_config_api import get_session_model_config
from app.model_config_service import provider_error_type, service_error
from app.case_lifecycle_service import default_template
from app.case_repository import CaseGenerationRepository
from app.case_schemas import (
    CandidateDraftEditInput, CandidateHistoryRecord, CandidateRemovalInput, CaseGeneration, CaseGenerationInput,
)
from app.case_service import _case_generation_context, build_candidates, template_limitations
from app.design_repository import DesignRepository
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.review_repository import RequirementReviewRepository
from app.template_repository import TemplateMappingRepository
from app.test_point_review_service import selected_test_points


def register_case_routes(
    app: FastAPI, projects: ProjectRepository, requirements: RequirementRepository,
    reviews: RequirementReviewRepository, designs: DesignRepository, templates: TemplateMappingRepository,
    generations: CaseGenerationRepository, ai_runs: AIRunRepository,
    mock_service: MockModelService, real_model_service: OpenAICompatibleModelService,
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        response_model=CaseGeneration, status_code=status.HTTP_201_CREATED,
    )
    def generate_cases(
        project_id: int, design_id: int, data: CaseGenerationInput,
        x_session_id: str | None = Header(default=None),
    ) -> CaseGeneration:
        _require_project(projects, project_id)
        design = designs.get(project_id, design_id)
        if design is None:
            raise HTTPException(status_code=404, detail="测试设计不存在")
        if design.status != "confirmed":
            raise HTTPException(status_code=409, detail="测试设计确认后才能生成候选测试用例")
        versions = requirements.list_versions(project_id)
        if not versions or versions[-1].id != design.requirement_version_id:
            raise HTTPException(status_code=409, detail="需求版本已更新，请基于当前版本重新确认测试设计后生成用例")
        version = requirements.get_version(project_id, design.requirement_version_id)
        review = reviews.latest_for_version(project_id, design.requirement_version_id)
        mapping_id = data.template_mapping_id
        if mapping_id is None:
            mapping, raw_content = default_template(project_id)
            mapping = templates.create(mapping, raw_content)
            mapping_id = mapping.id
        else:
            mapping = templates.get(project_id, mapping_id)
        if version is None or review is None or review.status != "confirmed":
            raise HTTPException(status_code=409, detail="需求确认后才能生成候选测试用例")
        test_point_review = review.test_point_review
        if test_point_review is None or test_point_review.status != "confirmed":
            raise HTTPException(status_code=409, detail="请先确认 Step 07～08 测试点审核")
        selected_points = selected_test_points(test_point_review)
        if not selected_points:
            raise HTTPException(status_code=409, detail="未选择测试点范围，不能生成候选测试用例")
        # 未解决冲突默认只排除受影响模块；严格模式才阻止整批生成。
        unresolved = [
            item for item in review.conflicts
            if item.decision in {"unresolved", "awaiting_external_confirmation"}
        ]
        blocked_modules = sorted({module for item in unresolved for module in item.affected_modules})
        if data.strict_conflicts and unresolved:
            raise HTTPException(
                status_code=409,
                detail={"code": "unresolved_requirement_conflicts", "modules": blocked_modules},
            )
        requested_modules = set(data.modules)
        if requested_modules.intersection(blocked_modules):
            raise HTTPException(
                status_code=409,
                detail={"code": "unresolved_requirement_conflicts", "modules": sorted(
                    requested_modules.intersection(blocked_modules)
                )},
            )
        excluded_modules = set(blocked_modules) if not data.strict_conflicts else set()
        point_modules = {
            item.test_item_id: item.module for item in test_point_review.test_items
        }
        generation_points = [
            point for point in selected_points
            if point_modules.get(point.test_item_id) not in excluded_modules
            and (not requested_modules or point_modules.get(point.test_item_id) in requested_modules)
        ]
        if not generation_points:
            raise HTTPException(status_code=409, detail="当前生成范围没有可用的已选测试点")
        if mapping is None or mapping.status != "confirmed":
            raise HTTPException(status_code=409, detail="模板映射确认后才能生成候选测试用例")
        limitations = template_limitations(mapping)
        if limitations and not data.accept_template_limitations:
            raise HTTPException(status_code=409, detail={"code": "template_limitations", "diagnostics": limitations})
        asset_versions = tuple(
            {"asset_id": item.asset_id, "revision": item.asset_revision} for item in version.materials
        )
        session_config = get_session_model_config(x_session_id) if data.mode == "real" else None
        if data.mode == "real" and session_config is None:
            raise HTTPException(status_code=422, detail="未配置真实模型；请先保存当前会话模型配置")
        model_parameters = AIModelConfig(
            provider=session_config.provider if session_config else "mock",
            model=session_config.model if session_config else "deterministic-v1",
        )
        project = projects.get(project_id)
        request = ModelRequest(
            task_type="case_generation", prompt_version="case-generation.v1", model_parameters=model_parameters,
            input_asset_versions=asset_versions, scenario=data.scenario,
            input_context=_case_generation_context(review, generation_points, project.software_version if project else ""),
            base_url=session_config.base_url if session_config else "",
            api_key=session_config.api_key if session_config else "",
        )
        service = real_model_service if data.mode == "real" else mock_service
        response = service.complete(request)
        output, errors, attempts, run_status, validation_status = _run(
            response, data.max_retries, asset_versions, data, service, request,
            {point.platform_test_point_id for point in generation_points},
        )
        run = ai_runs.create_run(AIRun(
            id=0, project_id=project_id, task_type="case_generation", model_parameters=model_parameters,
            prompt_version="case-generation.v1", input_asset_versions=list(asset_versions), output=output,
            validation_status=validation_status, validation_errors=errors, status=run_status,
            is_mock=data.mode == "mock",
            created_at=datetime.now(UTC), attempts=attempts,
        ))
        if run_status == "validation_failed":
            raise HTTPException(status_code=422, detail=service_error(
                "model_call", model_parameters.provider, model_parameters.model, "invalid_response", "schema_invalid",
            ).model_dump(mode="json") | {"ai_run_id": run.id})
        if run_status == "failed":
            error_code = next((item.error_code for item in reversed(attempts) if item.error_code), None)
            raise HTTPException(status_code=503, detail=service_error(
                "model_call", model_parameters.provider, model_parameters.model, provider_error_type(error_code),
            ).model_dump(mode="json") | {"ai_run_id": run.id})
        generation = CaseGeneration(
            id=0, project_id=project_id, design_id=design_id, requirement_version_id=design.requirement_version_id,
            template_mapping_id=mapping.id, ai_run_id=run.id, ai_run_status=run.status, is_mock=run.is_mock,
            status="empty" if not output["items"] else "succeeded",
            template_diagnostics=limitations, candidates=[], created_at=datetime.now(UTC),
        )
        if generation.status != "empty":
            selected_requirement_ids = {
                requirement_id for point in generation_points for requirement_id in point.stable_requirement_ids
            }
            selected_candidates = [
                item.candidate_id for item in review.atomic_requirements
                if item.stable_requirement_id in selected_requirement_ids
            ]
            generation.candidates = build_candidates(
                0, project_id, design, review, version, mapping, limitations, output["items"],
                selected_candidates, excluded_modules,
                None,
                project.software_version if project else "",
                generation_points,
            )
        return generations.create(generation)

    @router.get("/api/projects/{project_id}/case-generations", response_model=list[CaseGeneration])
    def list_cases(project_id: int) -> list[CaseGeneration]:
        _require_project(projects, project_id)
        return generations.list(project_id)

    @router.get("/api/projects/{project_id}/case-generations/{generation_id}", response_model=CaseGeneration)
    def get_cases(project_id: int, generation_id: int) -> CaseGeneration:
        _require_project(projects, project_id)
        generation = generations.get(project_id, generation_id)
        if generation is None:
            raise HTTPException(status_code=404, detail="候选测试用例生成记录不存在")
        return generation

    @router.patch(
        "/api/projects/{project_id}/case-generations/{generation_id}/candidates/{candidate_id}",
        response_model=CaseGeneration,
    )
    def edit_candidate(
        project_id: int, generation_id: int, candidate_id: str, data: CandidateDraftEditInput,
    ) -> CaseGeneration:
        _require_project(projects, project_id)
        generation = _require_generation(generations, project_id, generation_id)
        candidate = next((item for item in generation.candidates if item.id == candidate_id), None)
        if candidate is None:
            raise HTTPException(status_code=404, detail="候选测试用例不存在")
        updates = data.model_dump(exclude_none=True, exclude={"reason"})
        if not updates:
            raise HTTPException(status_code=422, detail="至少提供一个候选用例编辑字段")
        if "input" in updates and "steps" not in updates:
            updates["steps"] = [step.model_copy(update={"input": updates["input"]}) for step in candidate.steps]
        edited = candidate.model_copy(update=updates)
        generation.candidates = [edited if item.id == candidate_id else item for item in generation.candidates]
        generation.candidate_history.append(CandidateHistoryRecord(
            candidate_id=candidate_id, action="edited", reason=data.reason, created_at=datetime.now(UTC),
        ))
        return generations.save(generation, "candidate_edited")

    @router.patch(
        "/api/projects/{project_id}/case-generations/{generation_id}/candidates/{candidate_id}/removal",
        response_model=CaseGeneration,
    )
    def set_candidate_removal(
        project_id: int, generation_id: int, candidate_id: str, data: CandidateRemovalInput,
    ) -> CaseGeneration:
        _require_project(projects, project_id)
        generation = _require_generation(generations, project_id, generation_id)
        if not any(item.id == candidate_id for item in generation.candidates):
            raise HTTPException(status_code=404, detail="候选测试用例不存在")
        removed = set(generation.removed_candidate_ids)
        if data.removed:
            removed.add(candidate_id)
        else:
            removed.discard(candidate_id)
        generation.removed_candidate_ids = sorted(removed)
        generation.candidate_history.append(CandidateHistoryRecord(
            candidate_id=candidate_id, action="removed" if data.removed else "restored",
            reason=data.reason, created_at=datetime.now(UTC),
        ))
        return generations.save(generation, "candidate_removed" if data.removed else "candidate_restored")

    app.include_router(router)


def _run(
    response: object, max_retries: int, asset_versions: tuple[dict[str, int], ...], data: CaseGenerationInput,
    service: object, request: ModelRequest, allowed_test_point_ids: set[str],
):
    # 生成边界复用 AI 运行契约，确保失败只形成审计，不创建候选资产。
    attempts: list[AIAttempt] = []
    raw_response = response
    for number in range(1, max_retries + 2):
        started = datetime.now(UTC)
        error_code = getattr(raw_response, "error_code", None)
        retryable = bool(getattr(raw_response, "retryable", False))
        if error_code:
            attempts.append(AIAttempt(attempt=number, started_at=started, elapsed_ms=0, status="failed",
                                     error_code=error_code, retryable=retryable))
            if not retryable or number == max_retries + 1:
                return None, [], attempts, "failed", "not_run"
            raw_response = service.complete(request)
            continue
        output, errors = validate_case_generation_output(
            getattr(raw_response, "raw_output", None), allowed_test_point_ids,
        )
        if errors:
            attempts.append(AIAttempt(attempt=number, started_at=started, elapsed_ms=0, status="validation_failed",
                                     error_code="schema_invalid"))
            return None, errors, attempts, "validation_failed", "failed"
        attempts.append(AIAttempt(attempt=number, started_at=started, elapsed_ms=0, status="succeeded"))
        return output, [], attempts, "succeeded", "passed"
    return None, ["AI 运行没有产生结果"], attempts, "failed", "not_run"


def _require_project(repository: ProjectRepository, project_id: int) -> None:
    if repository.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")


def _require_generation(
    repository: CaseGenerationRepository, project_id: int, generation_id: int,
) -> CaseGeneration:
    generation = repository.get(project_id, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="候选测试用例生成记录不存在")
    return generation
