from collections import defaultdict

from fastapi import APIRouter, FastAPI, HTTPException, status

from app.execution_batch_repository import ExecutionBatchRepository
from app.execution_batch_schemas import ExecutionBatch
from app.execution_result_repository import ExecutionResultRepository
from app.execution_result_schemas import (
    BatchConclusionInput,
    CaseResultSummary,
    ExecutionBatchResults,
    ExecutionResultImportInput,
    ExecutionResultRecord,
    ResultConflict,
    ResultConflictResolutionInput,
    ResultMatchInput,
)
from app.repository import ProjectRepository


def register_execution_result_routes(
    app: FastAPI,
    projects: ProjectRepository,
    batches: ExecutionBatchRepository,
    results: ExecutionResultRepository,
) -> None:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/execution-batches/{batch_id}/results/import",
        response_model=ExecutionBatchResults,
        status_code=status.HTTP_201_CREATED,
    )
    def import_results(project_id: int, batch_id: int, data: ExecutionResultImportInput) -> ExecutionBatchResults:
        batch = _get_batch(projects, batches, project_id, batch_id)
        for item in data.results:
            if results.find_source(batch_id, data.source_type, item.source_record_id):
                continue
            match = _match_case(batch, item)
            retest_sequence = _retest_sequence(results, batch, item.retest_of_result_id)
            results.create(
                project_id, batch_id, data.source_type, item, match[0], match[1], None, match[2], match[3],
                retest_sequence or match[4], item.retest_of_result_id,
            )
            if match[0] == "matched":
                _detect_conflict(project_id, batch_id, results, match[2], retest_sequence or match[4])
        return _summary(results, batch_id)

    @router.get(
        "/api/projects/{project_id}/execution-batches/{batch_id}/results",
        response_model=ExecutionBatchResults,
    )
    def get_results(project_id: int, batch_id: int) -> ExecutionBatchResults:
        _get_batch(projects, batches, project_id, batch_id)
        return _summary(results, batch_id)

    @router.post(
        "/api/projects/{project_id}/execution-batches/{batch_id}/results/{result_id}/match",
        response_model=ExecutionBatchResults,
    )
    def match_result(project_id: int, batch_id: int, result_id: int, data: ResultMatchInput) -> ExecutionBatchResults:
        batch = _get_batch(projects, batches, project_id, batch_id)
        if data.decision == "matched":
            case = _case_by_identity(batch, data.stable_case_id, data.case_revision_id)
            if case is None:
                raise HTTPException(status_code=422, detail="人工匹配的稳定用例 ID 或修订版本不存在")
            updated = results.update_match(
                batch_id, result_id, "matched", data.stable_case_id, data.case_revision_id, data.reason,
                data.confirmer_name,
            )
            if updated is None or updated.batch_id != batch_id:
                raise HTTPException(status_code=404, detail="运行结果不存在")
            _detect_conflict(project_id, batch_id, results, data.stable_case_id, case.execution_sequence)
        else:
            if results.update_match(
                batch_id, result_id, "rejected", None, None, data.reason, data.confirmer_name
            ) is None:
                raise HTTPException(status_code=404, detail="运行结果不存在")
        return _summary(results, batch_id)

    @router.post(
        "/api/projects/{project_id}/execution-batches/{batch_id}/conflicts/{conflict_id}/resolve",
        response_model=ResultConflict,
    )
    def resolve_conflict(
        project_id: int, batch_id: int, conflict_id: int, data: ResultConflictResolutionInput
    ) -> ResultConflict:
        _get_batch(projects, batches, project_id, batch_id)
        conflict = results.resolve_conflict(conflict_id, data.decision, data.rationale, data.confirmer_name)
        if conflict is None or conflict.batch_id != batch_id:
            raise HTTPException(status_code=404, detail="结果冲突不存在")
        return conflict

    @router.post(
        "/api/projects/{project_id}/execution-batches/{batch_id}/conclusion",
        response_model=ExecutionBatchResults,
    )
    def confirm_conclusion(project_id: int, batch_id: int, data: BatchConclusionInput) -> ExecutionBatchResults:
        _get_batch(projects, batches, project_id, batch_id)
        summary = _summary(results, batch_id)
        if summary.unresolved_records:
            raise HTTPException(status_code=409, detail="仍有未完成人工匹配或拒绝的运行结果")
        if any(conflict.status == "open" for conflict in summary.conflicts):
            raise HTTPException(status_code=409, detail="仍有未处理的结果冲突")
        results.save_conclusion(batch_id, data.model_dump(mode="json"))
        return _summary(results, batch_id)

    app.include_router(router)


def _get_batch(
    projects: ProjectRepository, batches: ExecutionBatchRepository, project_id: int, batch_id: int
) -> ExecutionBatch:
    if projects.get(project_id) is None:
        raise HTTPException(status_code=404, detail="测试设计项目不存在")
    batch = batches.get(project_id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="执行批次不存在")
    return batch


def _case_by_identity(batch: ExecutionBatch, stable_case_id: str | None, case_revision_id: str | None):
    return next(
        (case for case in batch.cases
         if case.stable_case_id == stable_case_id and case.case_revision_id == case_revision_id),
        None,
    )


def _match_case(batch: ExecutionBatch, item):
    if item.stable_case_id and item.case_revision_id:
        case = _case_by_identity(batch, item.stable_case_id, item.case_revision_id)
        if case:
            return "matched", "按稳定用例 ID 和修订版本匹配", case.stable_case_id, case.case_revision_id, case.execution_sequence
        if any(case.stable_case_id == item.stable_case_id for case in batch.cases):
            return "unresolved", "稳定用例 ID 存在但修订版本不一致", None, None, None
        return "unresolved", "稳定用例 ID 未登记，等待人工匹配", None, None, None
    if item.external_case_number:
        candidates = [case for case in batch.cases if case.external_case_number == item.external_case_number]
        if len(candidates) == 1:
            case = candidates[0]
            if item.case_revision_id and item.case_revision_id != case.case_revision_id:
                return "unresolved", "外部编号对应的修订版本不一致", None, None, None
            return "matched", "按已登记外部用例编号匹配", case.stable_case_id, case.case_revision_id, case.execution_sequence
        if candidates:
            return "unresolved", "外部用例编号对应多个候选", None, None, None
    return "unresolved", "缺少可确定归属的稳定身份，等待人工匹配", None, None, None


def _retest_sequence(
    results: ExecutionResultRepository, batch: ExecutionBatch, retest_of_result_id: int | None
) -> int | None:
    if retest_of_result_id is None:
        return None
    records = results.list_records(batch.id)
    original = next((record for record in records if record.id == retest_of_result_id), None)
    if original is None or original.match_status != "matched":
        raise HTTPException(status_code=422, detail="复测关系必须引用同一批次中已匹配的运行结果")
    sequences = [case.execution_sequence for case in batch.cases if case.stable_case_id == original.stable_case_id]
    sequences.extend(
        record.execution_sequence or 0 for record in records if record.stable_case_id == original.stable_case_id
    )
    return max(sequences, default=0) + 1


def _detect_conflict(
    project_id: int, batch_id: int, results: ExecutionResultRepository, stable_case_id: str | None, sequence: int | None
) -> None:
    if stable_case_id is None or sequence is None:
        return
    records = [
        record for record in results.list_records(batch_id)
        if record.match_status == "matched" and record.stable_case_id == stable_case_id
        and record.execution_sequence == sequence
    ]
    comparable = {record.source_type: record for record in records}
    if len(comparable) < 2 or len({record.status for record in comparable.values()}) < 2:
        return
    if any(set(conflict.result_ids) == set(record.id for record in comparable.values())
           and conflict.status == "open" for conflict in results.list_conflicts(batch_id)):
        return
    results.create_conflict(
        project_id, batch_id, [record.id for record in comparable.values()],
        {record.source_type: record.status for record in comparable.values()},
    )


def _summary(results: ExecutionResultRepository, batch_id: int) -> ExecutionBatchResults:
    records = results.list_records(batch_id)
    grouped: dict[str, list[ExecutionResultRecord]] = defaultdict(list)
    for record in records:
        if record.match_status == "matched" and record.stable_case_id:
            grouped[record.stable_case_id].append(record)
    summaries = []
    for stable_case_id, case_records in grouped.items():
        ordered = sorted(case_records, key=lambda record: (record.execution_sequence or 0, record.id))
        summaries.append(CaseResultSummary(
            stable_case_id=stable_case_id, initial_result=ordered[0], latest_result=ordered[-1], history=ordered,
        ))
    conclusion = results.get_conclusion(batch_id)
    return ExecutionBatchResults(
        batch_id=batch_id, records=records,
        unresolved_records=[record for record in records if record.match_status == "unresolved"],
        conflicts=results.list_conflicts(batch_id), case_summaries=summaries, conclusion=conclusion,
    )
