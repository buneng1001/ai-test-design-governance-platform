from fastapi import HTTPException

from app.task_schemas import RunResultFeedback, TargetResultInput, TargetTaskContract, TestTask


def validate_target_extension(target: str, extension: dict[str, str]) -> None:
    allowed = {
        "manual": set(),
        "unspecified": set(),
        "test_execution_diagnostics": {"profile", "environment_ref"},
        "generic_automation": {"runner", "environment_ref"},
        "external_executor": {"executor_name", "environment_ref"},
    }[target]
    if set(extension) - allowed:
        raise HTTPException(status_code=422, detail="目标扩展字段不兼容")


def to_test_execution_task(task: TestTask, extension: dict[str, str]) -> TargetTaskContract:
    validate_target_extension("test_execution_diagnostics", extension)
    if task.execution_target != "test_execution_diagnostics":
        raise HTTPException(status_code=422, detail="任务执行目标不是测试执行与诊断平台")
    return TargetTaskContract(
        task_id=task.task_id,
        task_version=task.task_version,
        cases=task.cases,
        target_extension=extension,
    )


def from_test_execution_result(result: TargetResultInput) -> RunResultFeedback:
    return RunResultFeedback(
        task_id=result.task_id,
        task_version=result.task_version,
        stable_case_id=result.stable_case_id,
        case_revision_id=result.case_revision_id,
        verdict=result.verdict,
        evidence_references=result.evidence_references,
    )
