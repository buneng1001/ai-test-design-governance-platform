from datetime import UTC, datetime
import sqlite3
from time import sleep
from collections.abc import Callable

from fastapi import APIRouter, FastAPI, Header, HTTPException, status

from app.ai_repository import AIRunRepository
from app.ai_run_control_repository import AIRunControlRepository, BatchAlreadyClaimedError
from app.ai_run_control_repository import ConcurrentRunResumeError, InputFingerprintMismatchError
from app.ai_schemas import AIAttempt, AIRun, AIModelConfig
from app.ai_run_reliability import error_category, retry_delay_ms
from app.ai_service import ModelRequest, MockModelService, OpenAICompatibleModelService, local_structural_repair
from app.case_generation_contract import validate_case_generation_output
from app.model_config_api import get_session_model_config
from app.model_config_service import provider_error_type, service_error
from app.case_lifecycle_service import default_template
from app.case_repository import CaseGenerationRepository
from app.case_schemas import (
    CandidateDraftEditInput, CandidateHistoryRecord, CandidateRemovalInput, CandidateStandardExportInput, CaseGeneration, CaseGenerationInput,
)
from app.case_quality_service import STANDARD_COLUMNS, export_standard, quality_report_for_candidates, standard_rows_for_candidates
from fastapi.responses import Response
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
    generations: CaseGenerationRepository, ai_runs: AIRunRepository, controls: AIRunControlRepository,
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
        template_fallback = mapping is None or mapping.status != "confirmed"
        fallback_diagnostics: list[dict] = []
        if template_fallback:
            if mapping is None:
                raise HTTPException(status_code=404, detail="用例模板映射不存在")
            fallback_diagnostics = [*[
                item.model_dump() for item in mapping.diagnostics
            ], {"code": "template_mapping_fallback", "severity": "warning",
                "message": "自定义模板映射尚未确认，已改用平台标准用例表；可继续评审和导出"}]
            mapping, raw_content = default_template(project_id)
            mapping = templates.create(mapping, raw_content)
        mapping_limitations = template_limitations(mapping)
        if mapping_limitations and not data.accept_template_limitations:
            raise HTTPException(status_code=409, detail={"code": "template_limitations", "diagnostics": mapping_limitations})
        limitations = [*mapping_limitations, *fallback_diagnostics]
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
        service = real_model_service if data.mode == "real" else mock_service
        point_batches = [generation_points[index:index + data.batch_size]
                         for index in range(0, len(generation_points), data.batch_size)]
        control_payload = {
            "design_id": design_id, "requirement_version_id": design.requirement_version_id,
            "mapping_id": mapping.id, "point_ids": [item.platform_test_point_id for item in generation_points],
            "source_reference_ids": sorted({reference.reference_id for point in generation_points for reference in point.source_references}),
            "mode": data.mode, "variants": data.variants, "batch_size": data.batch_size,
            "accept_template_limitations": data.accept_template_limitations,
            "strict_conflicts": data.strict_conflicts, "modules": sorted(set(data.modules)),
        }
        fingerprint = controls.fingerprint(control_payload)
        control = controls.require(data.run_control_id) if data.run_control_id else controls.create(
            project_id, "case_generation", control_payload, len(point_batches),
        )
        if control.project_id != project_id or control.workflow != "case_generation" or control.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="运行输入已变化，不能恢复")
        if control.status == "completed" and control.final_asset_id is not None:
            existing = generations.get(project_id, control.final_asset_id)
            if existing is not None:
                return existing
        if data.start_only:
            return control.__dict__  # type: ignore[return-value]
        batch_outputs: list[dict] = [item["output"].get("model_output", item["output"])
                                   for item in controls.batch_results(control.id)]
        run_ids: list[int] = [item["ai_run_id"] for item in controls.batch_results(control.id)]
        run = None
        for batch_number, point_batch in enumerate(point_batches, start=1):
            if batch_number < control.next_batch:
                continue
            if controls.require(control.id).status != "running":
                raise HTTPException(status_code=409, detail={"message": "AI 运行已停止", "run_id": control.id})
            try:
                claim = controls.claim_next_batch(control.id)
            except BatchAlreadyClaimedError as exc:
                raise HTTPException(status_code=409, detail={"message": "AI 批次正在由其他恢复操作执行", "run_id": control.id}) from exc
            if claim.batch_number != batch_number:
                raise HTTPException(status_code=409, detail={"message": "AI 批次检查点已变化", "run_id": control.id})
            request = ModelRequest(
                task_type="case_generation", prompt_version="case-generation.v1", model_parameters=model_parameters,
                input_asset_versions=asset_versions, scenario=data.scenario,
                input_context=_case_generation_context(review, point_batch, project.software_version if project else ""),
                base_url=session_config.base_url if session_config else "",
                api_key=session_config.api_key if session_config else "",
            )
            response = service.complete(request)
            try:
                output, errors, attempts, run_status, validation_status = _run(
                    response, data.max_retries, asset_versions, data, service, request,
                    {point.platform_test_point_id for point in point_batch},
                    should_continue=lambda: controls.require(control.id).status == "running",
                )
            except CaseGenerationStopped as exc:
                controls.release_batch_claim(control.id, claim.lease_id)
                raise HTTPException(status_code=409, detail={"message": "AI 运行已停止", "run_id": control.id}) from exc
            run = ai_runs.create_run(AIRun(
                id=0, project_id=project_id, task_type="case_generation", model_parameters=model_parameters,
                prompt_version="case-generation.v1", input_asset_versions=list(asset_versions), output=output,
                validation_status=validation_status, validation_errors=errors, status=run_status,
                is_mock=data.mode == "mock", created_at=datetime.now(UTC), attempts=attempts,
                source="template" if data.mode == "template" else data.mode, stage="case_generation",
                batch_number=batch_number, batch_total=len(point_batches),
                completed_count=batch_number if output else batch_number - 1, total_count=len(generation_points),
                estimated_remaining_ms=max(0, (len(point_batches) - batch_number) * sum(
                    item.elapsed_ms for item in attempts
                )), recovery_point=f"case-generation.batch-{batch_number + 1}"
                if output and batch_number < len(point_batches) else None,
            ))
            run_ids.append(run.id)
            if run_status == "validation_failed":
                controls.release_batch_claim(control.id, claim.lease_id)
                raise HTTPException(status_code=422, detail=service_error(
                    "model_call", model_parameters.provider, model_parameters.model, "invalid_response", "schema_invalid",
                ).model_dump(mode="json") | {"ai_run_id": run.id, "batch_number": batch_number})
            if run_status == "failed":
                controls.release_batch_claim(control.id, claim.lease_id)
                error_code = next((item.error_code for item in reversed(attempts) if item.error_code), None)
                raise HTTPException(status_code=503, detail=service_error(
                    "model_call", model_parameters.provider, model_parameters.model, provider_error_type(error_code),
                ).model_dump(mode="json") | {"ai_run_id": run.id, "batch_number": batch_number})
            assert output is not None
            controls.record_validated_batch(control.id, batch_number, {
                "model_output": output,
                "source_reference_ids": [reference.reference_id for point in point_batch for reference in point.source_references],
            }, run.id, claim.lease_id)
            batch_outputs.append(output)
            if data.advance_only and batch_number < len(point_batches):
                return controls.require(control.id).__dict__  # type: ignore[return-value]
        if run is None and run_ids:
            run = ai_runs.get(project_id, run_ids[-1])
        assert run is not None
        output = {"contract_version": "case-generation.v1", "items": [
            item for batch_output in batch_outputs for item in batch_output["items"]
        ]}
        generation = CaseGeneration(
            id=0, project_id=project_id, design_id=design_id, requirement_version_id=design.requirement_version_id,
            template_mapping_id=mapping.id, ai_run_id=run.id, ai_run_status=run.status, is_mock=run.is_mock,
            ai_run_ids=run_ids, source=run.source, batch_total=len(point_batches), completed_batches=len(point_batches),
            run_control_id=control.id,
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
                generation_points, template_fallback,
            )
        if controls.require(control.id).status != "running":
            raise HTTPException(status_code=409, detail={"message": "AI 运行已停止", "run_id": control.id})
        try:
            created = generations.create(generation)
        except sqlite3.IntegrityError:
            created = generations.get_by_run_control(project_id, control.id)
            if created is None:
                raise
        controls.record_final_asset(control.id, "case_generation", created.id)
        controls.complete(control.id)
        return created

    @router.post("/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs", status_code=status.HTTP_201_CREATED)
    def start_case_generation_run(project_id: int, design_id: int, data: CaseGenerationInput) -> dict:
        return generate_cases(project_id, design_id, data.model_copy(update={"start_only": True}))  # type: ignore[return-value]

    def frozen_case_run_input(control, data: CaseGenerationInput, run_id: str) -> CaseGenerationInput:
        # 只允许省略已冻结参数；显式改动仍应被拒绝，避免恢复时悄悄改变可追溯的生成输入。
        payload_fields = {
            "template_mapping_id": "mapping_id", "mode": "mode", "batch_size": "batch_size",
            "variants": "variants", "accept_template_limitations": "accept_template_limitations",
            "strict_conflicts": "strict_conflicts", "modules": "modules",
        }
        for field, payload_field in payload_fields.items():
            if field in data.model_fields_set and getattr(data, field) != control.payload[payload_field]:
                raise HTTPException(status_code=409, detail="运行输入已变化，不能恢复")
        return data.model_copy(update={
            "template_mapping_id": control.payload["mapping_id"], "mode": control.payload["mode"],
            "batch_size": control.payload["batch_size"], "variants": control.payload["variants"],
            "accept_template_limitations": control.payload["accept_template_limitations"],
            "strict_conflicts": control.payload["strict_conflicts"], "modules": control.payload["modules"],
            "run_control_id": run_id, "advance_only": True,
        })

    @router.post("/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/advance")
    def advance_case_generation_run(project_id: int, design_id: int, run_id: str, data: CaseGenerationInput) -> dict:
        control = controls.require(run_id)
        if control.project_id != project_id or control.workflow != "case_generation":
            raise HTTPException(status_code=404, detail="AI 运行不存在")
        if control.payload.get("design_id") != design_id:
            raise HTTPException(status_code=409, detail="运行输入已变化，不能恢复")
        # 首次请求可能由默认模板自动创建映射；推进时必须复用控制记录冻结的输入，
        # 否则前端没有显式模板 ID 会重新创建映射，导致指纹不一致而无法继续。
        advanced = frozen_case_run_input(control, data, run_id)
        result = generate_cases(project_id, design_id, advanced)
        return result if isinstance(result, dict) else result.model_dump(mode="json")

    @router.post("/api/projects/{project_id}/test-designs/{design_id}/case-generation-runs/{run_id}/resume")
    def resume_case_generation_run(project_id: int, design_id: int, run_id: str, data: CaseGenerationInput) -> dict:
        control = controls.require(run_id)
        if control.project_id != project_id or control.workflow != "case_generation":
            raise HTTPException(status_code=404, detail="AI 运行不存在")
        if control.payload.get("design_id") != design_id:
            raise HTTPException(status_code=409, detail="运行输入已变化，不能恢复")
        try:
            controls.claim_resume(run_id, control.input_fingerprint)
        except InputFingerprintMismatchError as exc:
            raise HTTPException(status_code=409, detail="运行输入已变化，不能恢复") from exc
        except ConcurrentRunResumeError as exc:
            raise HTTPException(status_code=409, detail="已有恢复操作正在执行") from exc
        resumed = frozen_case_run_input(control, data, run_id)
        result = generate_cases(project_id, design_id, resumed)
        return result if isinstance(result, dict) else result.model_dump(mode="json")

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

    @router.get("/api/projects/{project_id}/case-generations/{generation_id}/standard-preview")
    def preview_generated_cases(project_id: int, generation_id: int) -> dict:
        _require_project(projects, project_id)
        generation = generations.get(project_id, generation_id)
        if generation is None:
            raise HTTPException(status_code=404, detail="候选测试用例不存在")
        project = projects.get(project_id)
        candidates = [item for item in generation.candidates if item.id not in generation.removed_candidate_ids]
        return {"columns": STANDARD_COLUMNS, "rows": standard_rows_for_candidates(candidates, project.software_version)}

    @router.get("/api/projects/{project_id}/case-generations/{generation_id}/quality-checks")
    def quality_check_generated_cases(project_id: int, generation_id: int) -> dict:
        _require_project(projects, project_id)
        generation = generations.get(project_id, generation_id)
        review = reviews.latest_for_version(project_id, generation.requirement_version_id) if generation else None
        if generation is None or review is None:
            raise HTTPException(status_code=409, detail="候选用例缺少需求审核上下文")
        candidates = [item for item in generation.candidates if item.id not in generation.removed_candidate_ids]
        return quality_report_for_candidates(review, candidates)

    @router.post("/api/projects/{project_id}/case-generations/{generation_id}/standard-export")
    def export_generated_cases(project_id: int, generation_id: int, data: CandidateStandardExportInput) -> Response:
        _require_project(projects, project_id)
        generation = generations.get(project_id, generation_id)
        if generation is None:
            raise HTTPException(status_code=404, detail="候选测试用例不存在")
        requested = set(data.candidate_ids)
        candidates = [item for item in generation.candidates if item.id not in generation.removed_candidate_ids
                      and (not requested or item.id in requested)]
        project = projects.get(project_id)
        content, media_type, extension = export_standard(
            standard_rows_for_candidates(candidates, project.software_version), data.format,
        )
        return Response(content=content, media_type=media_type, headers={
            "Content-Disposition": f'attachment; filename="candidate-test-cases.{extension}"',
        })

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


class CaseGenerationStopped(Exception):
    pass


def _run(
    response: object, max_retries: int, asset_versions: tuple[dict[str, int], ...], data: CaseGenerationInput,
    service: object, request: ModelRequest, allowed_test_point_ids: set[str], should_continue: Callable[[], bool],
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
                                     error_code=error_code, retryable=retryable,
                                     error_category=error_category(error_code),
                                     retry_after_ms=retry_delay_ms(number) if retryable else None,
                                     recovery_point=f"case-generation.retry-{number + 1}" if retryable else None))
            if not retryable or number == max_retries + 1:
                return None, [], attempts, "failed", "not_run"
            if not should_continue():
                raise CaseGenerationStopped()
            sleep(retry_delay_ms(number) / 1000)
            if not should_continue():
                raise CaseGenerationStopped()
            raw_response = service.complete(request)
            continue
        output, errors = validate_case_generation_output(
            getattr(raw_response, "raw_output", None), allowed_test_point_ids,
        )
        if errors:
            output, errors = validate_case_generation_output(
                local_structural_repair(getattr(raw_response, "raw_output", None)), allowed_test_point_ids,
            )
            if output is not None:
                attempts.append(AIAttempt(
                    attempt=number, started_at=started, elapsed_ms=0, status="succeeded",
                    error_code="schema_local_repaired", error_category="structure",
                    recovery_point="local_structural_repair",
                ))
                return output, [], attempts, "succeeded", "passed"
        if errors:
            attempts.append(AIAttempt(attempt=number, started_at=started, elapsed_ms=0, status="validation_failed",
                                     error_code="schema_invalid", error_category="structure",
                                     recovery_point="structural_repair_required"))
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
