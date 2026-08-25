import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, Response, status

from app.case_review_repository import CaseReviewRepository
from app.case_repository import CaseGenerationRepository
from app.design_repository import DesignRepository
from app.execution_batch_repository import ExecutionBatchRepository
from app.execution_batch_schemas import ExecutionBatch, ExecutionBatchCreateInput
from app.repository import ProjectRepository
from app.task_repository import TestTaskRepository
from app.task_schemas import TestTaskCase


def register_execution_batch_routes(
    app: FastAPI,
    projects: ProjectRepository,
    tasks: TestTaskRepository,
    reviews: CaseReviewRepository,
    generations: CaseGenerationRepository,
    designs: DesignRepository,
    batches: ExecutionBatchRepository,
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/test-tasks/{task_id}/execution-batches",
        response_model=ExecutionBatch,
        status_code=status.HTTP_201_CREATED,
    )
    def create_batch(project_id: int, task_id: str, data: ExecutionBatchCreateInput) -> ExecutionBatch:
        _require_project(projects, project_id)
        task = tasks.get(project_id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="测试任务不存在")
        if data.requirement_version_id != _task_requirement_version(
            project_id, task.case_review_batch_id, reviews, generations, designs
        ):
            raise HTTPException(status_code=409, detail="需求版本与已发布测试任务不一致")
        selected = _selected_task_cases(task.cases, data.stable_case_ids)
        sequences = batches.allocate_sequences(project_id, data.stable_case_ids)
        snapshots = [
            _snapshot(case, sequences[case.stable_case_id])
            for case in selected
        ]
        return batches.create(
            ExecutionBatch(
                id=0,
                project_id=project_id,
                test_task_id=task.task_id,
                test_task_version=task.task_version,
                product_version=data.product_version,
                requirement_version_id=data.requirement_version_id,
                environment=data.environment,
                scope=data.scope,
                responsible_person=data.responsible_person,
                execution_target=task.execution_target,
                cases=snapshots,
                created_at=datetime.now(UTC),
            )
        )

    @router.get(
        "/api/projects/{project_id}/execution-batches/{batch_id}",
        response_model=ExecutionBatch,
    )
    def get_batch(project_id: int, batch_id: int) -> ExecutionBatch:
        _require_project(projects, project_id)
        batch = batches.get(project_id, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="执行批次不存在")
        return batch

    @router.get("/api/projects/{project_id}/execution-batches/{batch_id}/manual-file")
    def download_manual_file(project_id: int, batch_id: int) -> Response:
        batch = get_batch(project_id, batch_id)
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=[
            "execution_record_id", "stable_case_id", "case_revision_id", "external_case_number",
            "execution_sequence", "display_number", "title", "filling_status", "actual_result",
            "reason", "executor", "executed_at", "evidence_references",
        ])
        writer.writeheader()
        for case in batch.cases:
            writer.writerow({
                "execution_record_id": f"batch-{batch.id}-seq-{case.execution_sequence}",
                "stable_case_id": case.stable_case_id,
                "case_revision_id": case.case_revision_id,
                "external_case_number": case.external_case_number or "",
                "execution_sequence": case.execution_sequence,
                "display_number": case.display_number,
                "title": case.title,
                "filling_status": "未填写",
                "actual_result": "",
                "reason": "",
                "executor": "",
                "executed_at": "",
                "evidence_references": "",
            })
        return Response(
            content="\ufeff" + output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="execution-batch-{batch.id}.csv"'},
        )

    app.include_router(router)


def _require_project(projects: ProjectRepository, project_id: int) -> None:
    if projects.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")


def _task_requirement_version(
    project_id: int,
    review_batch_id: int,
    reviews: CaseReviewRepository,
    generations: CaseGenerationRepository,
    designs: DesignRepository,
) -> int:
    review_batch = reviews.get(project_id, review_batch_id)
    if review_batch is None:
        raise HTTPException(status_code=404, detail="用例评审批次不存在")
    generation = generations.get(project_id, review_batch.generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="测试用例生成记录不存在")
    design = designs.get(project_id, generation.design_id)
    if design is None:
        raise HTTPException(status_code=404, detail="测试设计不存在")
    return design.requirement_version_id


def _selected_task_cases(cases: list[TestTaskCase], stable_case_ids: list[str]) -> list[TestTaskCase]:
    by_id = {case.stable_case_id: case for case in cases}
    if len(set(stable_case_ids)) != len(stable_case_ids):
        raise HTTPException(status_code=422, detail="执行范围不能重复选择稳定用例 ID")
    if any(case_id not in by_id for case_id in stable_case_ids):
        raise HTTPException(status_code=422, detail="执行范围包含不存在的稳定用例 ID")
    return [by_id[case_id] for case_id in stable_case_ids]


def _snapshot(case: TestTaskCase, sequence: int) -> dict:
    display_number = f"{case.external_case_number or case.stable_case_id}-{sequence}"
    return {
        **case.model_dump(),
        "execution_sequence": sequence,
        "display_number": display_number,
    }
