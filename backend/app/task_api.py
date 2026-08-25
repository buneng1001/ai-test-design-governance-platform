import hashlib
import json
from datetime import UTC, datetime

import yaml
from fastapi import APIRouter, FastAPI, HTTPException, Response, status

from app.case_review_repository import CaseReviewRepository
from app.case_review_schemas import CaseReviewBatch, CaseRevision
from app.repository import ProjectRepository
from app.task_adapter import from_test_execution_result, to_test_execution_task, validate_target_extension
from app.task_repository import TestTaskRepository
from app.task_schemas import (
    AdapterConversionInput,
    RunResultFeedback,
    TargetResultInput,
    TargetTaskContract,
    TaskPublicationInput,
    TestTask,
)


def register_task_routes(
    app: FastAPI, projects: ProjectRepository, reviews: CaseReviewRepository, tasks: TestTaskRepository
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/case-review-batches/{batch_id}/test-tasks",
        response_model=TestTask,
        status_code=status.HTTP_201_CREATED,
    )
    def publish_task(project_id: int, batch_id: int, data: TaskPublicationInput) -> TestTask:
        _require_project(projects, project_id)
        batch = reviews.get(project_id, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="评审批次不存在")
        if batch.status != "confirmed":
            raise HTTPException(status_code=409, detail="用例确认后才能完成发布确认")
        validate_target_extension(data.execution_target, data.target_extension)
        selected = _selected_cases(batch, data.stable_case_ids)
        task_id = "task-" + hashlib.sha256(
            f"{project_id}:{batch_id}:{data.stable_case_ids}".encode()
        ).hexdigest()[:12]
        previous = tasks.get(project_id, task_id)
        task = TestTask(
            task_id=task_id,
            task_version=(previous.task_version + 1) if previous else 1,
            project_id=project_id,
            case_review_batch_id=batch_id,
            execution_target=data.execution_target,
            cases=[_to_task_case(item) for item in selected],
            published_by=data.confirmer_name,
            published_at=datetime.now(UTC),
        )
        return tasks.create(task)

    @router.get("/api/projects/{project_id}/test-tasks/{task_id}", response_model=TestTask)
    def get_task(project_id: int, task_id: str) -> TestTask:
        _require_project(projects, project_id)
        task = tasks.get(project_id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="测试任务不存在")
        return task

    @router.get("/api/projects/{project_id}/test-tasks/{task_id}/download")
    def download_task(project_id: int, task_id: str, format: str = "json") -> Response:
        task = get_task(project_id, task_id)
        if format not in {"json", "yaml"}:
            raise HTTPException(status_code=422, detail="只支持 JSON 或 YAML")
        payload = task.model_dump(mode="json")
        if format == "json":
            content, media_type = json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        else:
            content = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
            media_type = "application/yaml"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{task_id}.{format}"'},
        )

    @router.post("/api/test-task-adapters/test-execution-diagnostics", response_model=TargetTaskContract)
    def adapt_task(data: AdapterConversionInput) -> TargetTaskContract:
        return to_test_execution_task(data.task, data.target_extension)

    @router.post(
        "/api/test-task-adapters/test-execution-diagnostics/results", response_model=RunResultFeedback
    )
    def adapt_result(data: TargetResultInput) -> RunResultFeedback:
        return from_test_execution_result(data)

    app.include_router(router)


def _require_project(projects: ProjectRepository, project_id: int) -> None:
    if projects.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")


def _selected_cases(batch: CaseReviewBatch, stable_case_ids: list[str]) -> list[CaseRevision]:
    by_id = {
        item.stable_case_id: item
        for item in batch.revisions
        if item.participation_status == "included" and item.stable_case_id is not None
    }
    if any(case_id not in by_id for case_id in stable_case_ids):
        raise HTTPException(status_code=422, detail="执行范围包含不存在或未纳入的稳定用例 ID")
    return [by_id[case_id] for case_id in stable_case_ids]


def _to_task_case(revision: CaseRevision) -> dict:
    candidate = revision.candidate
    return {
        "stable_case_id": revision.stable_case_id,
        "case_revision_id": revision.id,
        "case_revision": revision.revision,
        "title": candidate.title,
        "priority": candidate.priority,
        "preconditions": candidate.preconditions,
        "parameters": {},
        "steps": [step.model_dump() for step in candidate.steps],
        "expected_result": candidate.overall_expectation,
        "verdict_method": "expected_result_match",
        "evidence_requirements": candidate.evidence_requirements,
    }
