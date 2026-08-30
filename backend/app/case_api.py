from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, status

from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIRun, AIModelConfig
from app.ai_service import ModelRequest, MockModelService, validate_output
from app.case_repository import CaseGenerationRepository
from app.case_schemas import CaseGeneration, CaseGenerationInput
from app.case_service import build_candidates, template_limitations
from app.design_repository import DesignRepository
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.review_repository import RequirementReviewRepository
from app.template_repository import TemplateMappingRepository


def register_case_routes(
    app: FastAPI, projects: ProjectRepository, requirements: RequirementRepository,
    reviews: RequirementReviewRepository, designs: DesignRepository, templates: TemplateMappingRepository,
    generations: CaseGenerationRepository, ai_runs: AIRunRepository,
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        response_model=CaseGeneration, status_code=status.HTTP_201_CREATED,
    )
    def generate_cases(project_id: int, design_id: int, data: CaseGenerationInput) -> CaseGeneration:
        _require_project(projects, project_id)
        design = designs.get(project_id, design_id)
        if design is None:
            raise HTTPException(status_code=404, detail="测试设计不存在")
        if design.status != "confirmed":
            raise HTTPException(status_code=409, detail="测试设计确认后才能生成候选测试用例")
        version = requirements.get_version(project_id, design.requirement_version_id)
        review = reviews.latest_for_version(project_id, design.requirement_version_id)
        mapping = templates.get(project_id, data.template_mapping_id)
        if version is None or review is None or review.status != "confirmed":
            raise HTTPException(status_code=409, detail="需求确认后才能生成候选测试用例")
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
        affected = sorted(requested_modules.intersection(blocked_modules)) if requested_modules else blocked_modules
        if affected:
            raise HTTPException(
                status_code=409,
                detail={"code": "unresolved_requirement_conflicts", "modules": affected},
            )
        excluded_modules = set(blocked_modules) if not data.strict_conflicts else set()
        if mapping is None or mapping.status != "confirmed":
            raise HTTPException(status_code=409, detail="模板映射确认后才能生成候选测试用例")
        limitations = template_limitations(mapping)
        if limitations and not data.accept_template_limitations:
            raise HTTPException(status_code=409, detail={"code": "template_limitations", "diagnostics": limitations})
        asset_versions = tuple(
            {"asset_id": item.asset_id, "revision": item.asset_revision} for item in version.materials
        )
        response = MockModelService().complete(ModelRequest(
            task_type="case_generation", prompt_version="case-generation.v1", model_parameters=AIModelConfig(),
            input_asset_versions=asset_versions, scenario=data.scenario,
        ))
        output, errors, attempts, run_status, validation_status = _run(response, data.max_retries, asset_versions, data)
        run = ai_runs.create_run(AIRun(
            id=0, project_id=project_id, task_type="case_generation", model_parameters=AIModelConfig(),
            prompt_version="case-generation.v1", input_asset_versions=list(asset_versions), output=output,
            validation_status=validation_status, validation_errors=errors, status=run_status, is_mock=True,
            created_at=datetime.now(UTC), attempts=attempts,
        ))
        if run_status == "validation_failed":
            raise HTTPException(status_code=422, detail={"code": "ai_output_invalid", "ai_run_id": run.id})
        if run_status == "failed":
            raise HTTPException(status_code=503, detail={"code": "ai_run_failed", "ai_run_id": run.id})
        generation = CaseGeneration(
            id=0, project_id=project_id, design_id=design_id, requirement_version_id=design.requirement_version_id,
            template_mapping_id=mapping.id, ai_run_id=run.id, ai_run_status=run.status, is_mock=run.is_mock,
            status="empty" if not output["items"] else "succeeded",
            template_diagnostics=limitations, candidates=[], created_at=datetime.now(UTC),
        )
        if generation.status != "empty":
            project = projects.get(project_id)
            generation.candidates = build_candidates(
                0, project_id, design, review, version, mapping, data.variants, limitations,
                review.selected_requirement_ids, excluded_modules,
                set(data.modules),
                project.software_version if project else "",
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

    app.include_router(router)


def _run(response: object, max_retries: int, asset_versions: tuple[dict[str, int], ...], data: CaseGenerationInput):
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
            raw_response = MockModelService().complete(ModelRequest(
                task_type="case_generation", prompt_version="case-generation.v1", model_parameters=AIModelConfig(),
                input_asset_versions=asset_versions, scenario=data.scenario,
            ))
            continue
        output, errors = validate_output(getattr(raw_response, "raw_output", None))
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
