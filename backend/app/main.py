import os
from datetime import UTC, datetime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from app.ai_repository import AIRunRepository
from app.ai_schemas import AIAttempt, AIDispositionInput, AIRun, AIRunInput, AIModelConfig
from app.ai_service import ModelRequest, MockModelService, UnavailableModelService, validate_output
from app.asset_repository import AssetRepository
from app.case_api import register_case_routes
from app.case_review_api import register_case_review_routes
from app.case_review_repository import CaseReviewRepository
from app.case_repository import CaseGenerationRepository
from app.design_repository import DesignRepository
from app.design_api import register_design_routes
from app.asset_schemas import AssetContentInput, AssetProvenanceInput, AssetProvenanceRecord, HashVerification
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.requirement_schemas import RequirementPackage, RequirementPackageInput, RequirementVersion
from app.requirement_service import build_requirement_package
from app.review_repository import RequirementReviewRepository
from app.review_schemas import AtomicRequirementUpdate, FindingUpdate, RequirementAnalysis
from app.review_schemas import RequirementConfirmationInput, RequirementReviewFinding, VisualInferenceUpdate
from app.review_service import build_analysis_candidates, source_reference_exists
from app.schemas import Project, ProjectInput
from app.template_api import register_template_routes
from app.template_repository import TemplateMappingRepository
from app.task_api import register_task_routes
from app.task_repository import TestTaskRepository
from app.execution_batch_api import register_execution_batch_routes
from app.execution_batch_repository import ExecutionBatchRepository
from app.execution_result_api import register_execution_result_routes
from app.execution_result_repository import ExecutionResultRepository
from app.quality_api import register_quality_routes
from app.quality_repository import QualityRepository
from app.change_impact_api import register_change_impact_routes
from app.change_impact_repository import ChangeImpactRepository
def create_app(database_path: Path | None = None) -> FastAPI:
    resolved_database_path = database_path or Path(os.getenv("APP_DATABASE_PATH", "data/app.db"))
    repository = ProjectRepository(resolved_database_path)
    asset_repository = AssetRepository(resolved_database_path)
    requirement_repository = RequirementRepository(resolved_database_path)
    review_repository = RequirementReviewRepository(resolved_database_path)
    design_repository = DesignRepository(resolved_database_path)
    ai_run_repository = AIRunRepository(resolved_database_path)
    template_repository = TemplateMappingRepository(resolved_database_path)
    case_generation_repository = CaseGenerationRepository(resolved_database_path)
    case_review_repository = CaseReviewRepository(resolved_database_path)
    task_repository = TestTaskRepository(resolved_database_path)
    execution_batch_repository = ExecutionBatchRepository(resolved_database_path)
    execution_result_repository = ExecutionResultRepository(resolved_database_path)
    quality_repository = QualityRepository(resolved_database_path)
    change_impact_repository = ChangeImpactRepository(resolved_database_path)
    model_service = MockModelService()
    unavailable_model_service = UnavailableModelService()
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        repository.migrate()
        yield
    app = FastAPI(title="AI 测试设计与治理平台", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_design_routes(
        app, repository, requirement_repository, review_repository, design_repository, ai_run_repository
    )
    register_template_routes(app, repository, template_repository)
    register_case_routes(
        app, repository, requirement_repository, review_repository, design_repository, template_repository,
        case_generation_repository, ai_run_repository,
    )
    register_case_review_routes(
        app, repository, case_generation_repository, case_review_repository, ai_run_repository, requirement_repository,
        template_repository,
    )
    register_task_routes(app, repository, case_review_repository, task_repository)
    register_execution_batch_routes(
        app, repository, task_repository, case_review_repository, case_generation_repository,
        design_repository, execution_batch_repository,
    )
    register_execution_result_routes(app, repository, execution_batch_repository, execution_result_repository)
    register_quality_routes(
        app, repository, requirement_repository, review_repository, design_repository, case_review_repository,
        case_generation_repository,
        execution_batch_repository, execution_result_repository, quality_repository, ai_run_repository,
    )
    register_change_impact_routes(
        app, repository, requirement_repository, review_repository, design_repository, case_review_repository,
        execution_batch_repository, execution_result_repository, quality_repository, task_repository,
        ai_run_repository, change_impact_repository,
    )
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}
    @app.post("/api/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
    def create_project(project_input: ProjectInput) -> Project:
        return repository.create(project_input)
    @app.get("/api/projects", response_model=list[Project])
    def list_projects() -> list[Project]:
        return repository.list()
    @app.get("/api/projects/{project_id}", response_model=Project)
    def get_project(project_id: int) -> Project:
        return require_project(repository.get(project_id))
    @app.put("/api/projects/{project_id}", response_model=Project)
    def update_project(project_id: int, project_input: ProjectInput) -> Project:
        return require_project(repository.update(project_id, project_input))
    @app.post(
        "/api/projects/{project_id}/assets",
        response_model=AssetProvenanceRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def create_asset(project_id: int, asset_input: AssetProvenanceInput) -> AssetProvenanceRecord:
        require_project(repository.get(project_id))
        return asset_repository.create(project_id, asset_input)
    @app.get("/api/projects/{project_id}/assets", response_model=list[AssetProvenanceRecord])
    def list_assets(project_id: int) -> list[AssetProvenanceRecord]:
        require_project(repository.get(project_id))
        return asset_repository.list_assets(project_id)
    @app.put("/api/projects/{project_id}/assets/{asset_id}", response_model=AssetProvenanceRecord)
    def revise_asset(
        project_id: int,
        asset_id: int,
        asset_input: AssetProvenanceInput,
    ) -> AssetProvenanceRecord:
        require_project(repository.get(project_id))
        return require_asset(asset_repository.revise(project_id, asset_id, asset_input))
    @app.get(
        "/api/projects/{project_id}/assets/{asset_id}/history",
        response_model=list[AssetProvenanceRecord],
    )
    def get_asset_history(project_id: int, asset_id: int) -> list[AssetProvenanceRecord]:
        require_project(repository.get(project_id))
        history = asset_repository.history(project_id, asset_id)
        if history is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产来源记录不存在")
        return history
    @app.post(
        "/api/projects/{project_id}/assets/{asset_id}/verify",
        response_model=HashVerification,
    )
    def verify_asset_hash(
        project_id: int,
        asset_id: int,
        content: AssetContentInput,
    ) -> HashVerification:
        require_project(repository.get(project_id))
        asset = require_asset(asset_repository.get(project_id, asset_id))
        actual_sha256 = asset_repository.hash_content(content.content_base64)
        return HashVerification(
            matches=asset.sha256 == actual_sha256,
            expected_sha256=asset.sha256,
            actual_sha256=actual_sha256,
        )
    @app.get(
        "/api/projects/{project_id}/model-context-assets",
        response_model=list[AssetProvenanceRecord],
    )
    def get_model_context_assets(project_id: int) -> list[AssetProvenanceRecord]:
        require_project(repository.get(project_id))
        return asset_repository.model_context_assets(project_id)
    @app.post(
        "/api/projects/{project_id}/requirement-packages",
        response_model=RequirementPackage,
        status_code=status.HTTP_201_CREATED,
    )
    def create_requirement_package(
        project_id: int,
        package_input: RequirementPackageInput,
    ) -> RequirementPackage:
        require_project(repository.get(project_id))
        package = build_requirement_package(project_id, package_input, asset_repository)
        return requirement_repository.create_package(package)
    @app.get(
        "/api/projects/{project_id}/requirement-packages/{package_id}",
        response_model=RequirementPackage,
    )
    def get_requirement_package(project_id: int, package_id: int) -> RequirementPackage:
        require_project(repository.get(project_id))
        package = requirement_repository.get_package(project_id, package_id)
        if package is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="需求资料包不存在")
        return package
    @app.post(
        "/api/projects/{project_id}/requirement-packages/{package_id}/publish",
        response_model=RequirementVersion,
        status_code=status.HTTP_201_CREATED,
    )
    def publish_requirement_package(project_id: int, package_id: int) -> RequirementVersion:
        require_project(repository.get(project_id))
        package = requirement_repository.get_package(project_id, package_id)
        if package is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="需求资料包不存在")
        if package.published_version_id is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="需求资料包已经发布")
        if not any(material.parse_status in {"complete", "partial"} for material in package.materials):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="需求资料包没有可发布的完整解析结果",
            )
        version = requirement_repository.publish(package)
        if version is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="需求资料包已经发布")
        return version
    @app.get(
        "/api/projects/{project_id}/requirement-versions",
        response_model=list[RequirementVersion],
    )
    def list_requirement_versions(project_id: int) -> list[RequirementVersion]:
        require_project(repository.get(project_id))
        return requirement_repository.list_versions(project_id)
    @app.get(
        "/api/projects/{project_id}/requirement-versions/{version_id}",
        response_model=RequirementVersion,
    )
    def get_requirement_version(project_id: int, version_id: int) -> RequirementVersion:
        require_project(repository.get(project_id))
        version = requirement_repository.get_version(project_id, version_id)
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="需求版本不存在")
        return version
    @app.post(
        "/api/projects/{project_id}/requirement-versions/{version_id}/requirement-review",
        response_model=RequirementAnalysis,
        status_code=status.HTTP_201_CREATED,
    )
    def create_requirement_review(project_id: int, version_id: int) -> RequirementAnalysis:
        require_project(repository.get(project_id))
        version = requirement_repository.get_version(project_id, version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="需求版本不存在")
        existing = review_repository.latest_for_version(project_id, version_id)
        if existing is not None:
            return existing
        atomic_requirements, findings, visual_inferences = build_analysis_candidates(version)
        input_asset_versions = [
            {"asset_id": material.asset_id, "revision": material.asset_revision}
            for material in version.materials
        ]
        ai_run = ai_run_repository.create_run(
            AIRun(
                id=0,
                project_id=project_id,
                task_type="requirement_review",
                model_parameters=AIModelConfig(),
                prompt_version="requirement-review.v1",
                input_asset_versions=input_asset_versions,
                output={
                    "contract_version": "ai-output.v1",
                    "items": [
                        {
                            "candidate_id": item.candidate_id,
                            "summary": item.statement,
                            "source_asset_ids": [item.source_reference.asset_id],
                        }
                        for item in atomic_requirements
                    ],
                },
                validation_status="passed",
                validation_errors=[],
                status="succeeded",
                is_mock=True,
                created_at=datetime.now(UTC),
                attempts=[
                    AIAttempt(
                        attempt=1,
                        started_at=datetime.now(UTC),
                        elapsed_ms=0,
                        status="succeeded",
                    )
                ],
            )
        )
        analysis = RequirementAnalysis(
            id=0,
            project_id=project_id,
            requirement_version_id=version_id,
            atomic_requirements=atomic_requirements,
            findings=findings,
            visual_inferences=visual_inferences,
            ai_run_id=ai_run.id,
        )
        return review_repository.create(analysis)
    @app.get(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}",
        response_model=RequirementAnalysis,
    )
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
        project_id: int,
        analysis_id: int,
        candidate_id: str,
        update: AtomicRequirementUpdate,
    ) -> RequirementAnalysis:
        analysis = require_review(repository, review_repository, project_id, analysis_id)
        candidate = next(
            (item for item in analysis.atomic_requirements if item.candidate_id == candidate_id), None
        )
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
                analysis.atomic_requirements.append(
                    candidate.model_copy(
                        update={
                            "candidate_id": f"{candidate.candidate_id}-split-{index}",
                            "stable_requirement_id": None,
                            "statement": statement,
                            "decision": "pending_confirmation",
                            "created_at": now,
                            "updated_at": now,
                        }
                    )
                )
        if update.merge_candidate_ids:
            merge_ids = {candidate_id, *update.merge_candidate_ids}
            merge_candidates = [
                item for item in analysis.atomic_requirements if item.candidate_id in merge_ids
            ]
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
        project_id: int,
        analysis_id: int,
        finding_id: str,
        update: FindingUpdate,
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
        project_id: int,
        analysis_id: int,
        inference_id: str,
        update: VisualInferenceUpdate,
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
    @app.post(
        "/api/projects/{project_id}/requirement-reviews/{analysis_id}/confirm",
        response_model=RequirementAnalysis,
    )
    def confirm_requirement_review(
        project_id: int,
        analysis_id: int,
        confirmation: RequirementConfirmationInput,
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
        analysis.status = "confirmed"
        analysis.confirmed_by = confirmation.confirmer_name
        analysis.confirmed_at = datetime.now(UTC)
        return review_repository.save(analysis, "requirement_confirmed")
    register_design_routes(
        app, repository, requirement_repository, review_repository, design_repository, ai_run_repository
    )
    @app.post("/api/projects/{project_id}/ai-runs", response_model=AIRun, status_code=status.HTTP_201_CREATED)
    def create_ai_run(project_id: int, run_input: AIRunInput) -> AIRun:
        require_project(repository.get(project_id))
        input_asset_versions = []
        for asset_id in run_input.input_asset_ids:
            asset = asset_repository.get(project_id, asset_id)
            if asset is None:
                raise HTTPException(status_code=404, detail="AI 运行输入资产不存在")
            if not asset.can_enter_model_context:
                raise HTTPException(status_code=422, detail="来源不明资产或评估真值不能进入模型上下文")
            input_asset_versions.append({"asset_id": asset.id, "revision": asset.revision})
        attempts = []
        final_output = None
        validation_errors: list[str] = []
        run_status = "failed"
        validation_status = "not_run"
        max_attempts = run_input.max_retries + 1
        request = ModelRequest(
            task_type=run_input.task_type,
            prompt_version=run_input.prompt_version,
            model_parameters=run_input.model_parameters,
            input_asset_versions=tuple(input_asset_versions),
            scenario=run_input.scenario,
        )
        selected_model_service = (
            model_service if run_input.model_parameters.provider == "mock" else unavailable_model_service
        )
        for attempt_number in range(1, max_attempts + 1):
            started_at = datetime.now(UTC)
            response = selected_model_service.complete(request)
            elapsed_ms = max(0, int((datetime.now(UTC) - started_at).total_seconds() * 1000))
            if response.error_code:
                attempts.append({
                    "attempt": attempt_number, "started_at": started_at, "elapsed_ms": elapsed_ms,
                    "status": "failed", "error_code": response.error_code, "retryable": response.retryable,
                })
                if not response.retryable or attempt_number == max_attempts:
                    break
                continue
            output, validation_errors = validate_output(response.raw_output)
            if validation_errors:
                attempts.append({
                    "attempt": attempt_number, "started_at": started_at, "elapsed_ms": elapsed_ms,
                    "status": "validation_failed", "error_code": "schema_invalid", "retryable": False,
                })
                validation_status = "failed"
                run_status = "validation_failed"
                break
            final_output = output
            validation_status = "passed"
            run_status = "succeeded"
            attempts.append({
                "attempt": attempt_number, "started_at": started_at, "elapsed_ms": elapsed_ms,
                "status": "succeeded", "error_code": None, "retryable": False,
            })
            break
        run = AIRun(
            id=0, project_id=project_id, task_type=run_input.task_type, model_parameters=run_input.model_parameters,
            prompt_version=run_input.prompt_version, input_asset_versions=input_asset_versions,
            output=final_output, validation_status=validation_status, validation_errors=validation_errors,
            status=run_status, is_mock=run_input.model_parameters.provider == "mock",
            created_at=datetime.now(UTC), attempts=attempts,
        )
        return ai_run_repository.create_run(run)
    @app.get("/api/projects/{project_id}/ai-runs", response_model=list[AIRun])
    def list_ai_runs(project_id: int) -> list[AIRun]:
        require_project(repository.get(project_id))
        return ai_run_repository.list(project_id)
    @app.get("/api/projects/{project_id}/ai-runs/audit-export")
    def export_ai_audit(project_id: int) -> dict:
        require_project(repository.get(project_id))
        return {
            "contract_version": "ai-audit.v1",
            "project_id": project_id,
            "runs": [run.model_dump(mode="json") for run in ai_run_repository.list(project_id)],
        }
    @app.get("/api/projects/{project_id}/ai-runs/{run_id}", response_model=AIRun)
    def get_ai_run(project_id: int, run_id: int) -> AIRun:
        require_project(repository.get(project_id))
        run = ai_run_repository.get(project_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="AI 运行不存在")
        return run
    @app.post("/api/projects/{project_id}/ai-runs/{run_id}/dispositions", response_model=AIRun)
    def create_ai_disposition(
        project_id: int, run_id: int, disposition: AIDispositionInput
    ) -> AIRun:
        require_project(repository.get(project_id))
        run = ai_run_repository.add_disposition(project_id, run_id, disposition)
        if run is None:
            raise HTTPException(status_code=404, detail="AI 运行不存在")
        return run
    return app
def require_project(project: Project | None) -> Project:
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试设计项目不存在")
    return project
def require_asset(asset: AssetProvenanceRecord | None) -> AssetProvenanceRecord:
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产来源记录不存在")
    return asset
def require_review(
    repository: ProjectRepository,
    review_repository: RequirementReviewRepository,
    project_id: int,
    analysis_id: int,
) -> RequirementAnalysis:
    require_project(repository.get(project_id))
    analysis = review_repository.get(project_id, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="需求评审不存在")
    return analysis

app = create_app()
