"""仅用于 RC2 发布验收失败后的本地脱敏诊断与离线回放。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import uuid4

from app.ai_output_processing import local_structural_repair, validate_requirement_analysis_output
from app.ai_service import ModelRequest, ModelResponse, extract_structured_content
from app.case_generation_contract import validate_case_generation_output
from app.review_schemas import StructuredAnalysisOutput


_SECRET_FIELD = re.compile(r"(api[._-]?key|authorization|access[._-]?token|secret|password)", re.IGNORECASE)
_BEARER_VALUE = re.compile(r"Bearer\s+[^\s\"']+", re.IGNORECASE)


def record_real_model_failure(
    request: ModelRequest,
    failure_stage: str,
    response: ModelResponse,
    schema_errors: list[str] | None = None,
) -> Path | None:
    """在显式指定的 Git 忽略目录保存失败响应；未配置目录时完全不落盘。"""
    destination = _local_diagnostic_directory()
    if destination is None or not request.api_key:
        return None
    destination.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": request.model_parameters.provider,
        "model": request.model_parameters.model,
        "task_type": request.task_type,
        "failure_stage": failure_stage,
        "http_status": response.http_status,
        "error_code": response.error_code,
        "finish_reason": response.finish_reason,
        "response_length": response.response_length,
        "schema_errors": [
            _redact_value(str(error), request.api_key) for error in list(schema_errors or [])[:10]
        ],
        "input_context": _redact_value(request.input_context, request.api_key),
        "raw_output": _redact_value(response.raw_output, request.api_key),
        "provider_response": _redact_value(response.provider_response, request.api_key),
    }
    path = destination / f"rc2-real-model-failure-{uuid4().hex}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _local_diagnostic_directory() -> Path | None:
    configured = os.getenv("RC2_LOCAL_DIAGNOSTIC_DIR")
    if not configured:
        return None
    destination = Path(configured).resolve()
    expected = (Path.cwd() / ".ticket11-release-diagnostics").resolve()
    return destination if destination == expected else None


def replay_release_diagnostic(path: Path) -> dict[str, str]:
    """仅以本地捕获数据重放每个契约阶段，不发起任何网络请求。"""
    diagnostic = json.loads(path.read_text(encoding="utf-8"))
    stages = {
        "json_extraction": "not_run",
        "structural_repair": "not_run",
        "requirement_schema": "not_applicable",
        "source_relationships": "not_applicable",
        "case_schema": "not_applicable",
    }
    provider_response = diagnostic.get("provider_response")
    try:
        raw_output = extract_structured_content(provider_response) if provider_response else diagnostic.get("raw_output")
        stages["json_extraction"] = "passed"
    except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        stages["json_extraction"] = "failed"
        stages["minimal_failure_stage"] = "json_extraction"
        return stages

    repaired = local_structural_repair(raw_output)
    stages["structural_repair"] = "passed"
    context = tuple(item for item in diagnostic.get("input_context", []) if isinstance(item, dict))
    if diagnostic.get("task_type") == "requirement_review":
        output, errors = validate_requirement_analysis_output(repaired, context)
        if errors or output is None:
            stages["requirement_schema"] = "failed"
            stages["source_relationships"] = "not_run"
            stages["minimal_failure_stage"] = "requirement_schema"
            return stages
        stages["requirement_schema"] = "passed"
        relationship_errors = _source_relationship_errors(output)
        stages["source_relationships"] = "failed" if relationship_errors else "passed"
        stages["minimal_failure_stage"] = "source_relationships" if relationship_errors else "none"
        return stages

    if diagnostic.get("task_type") == "case_generation":
        allowed = {
            str(item["platform_test_point_id"])
            for item in context if item.get("platform_test_point_id") is not None
        }
        output, errors = validate_case_generation_output(repaired, allowed)
        stages["case_schema"] = "failed" if errors or output is None else "passed"
        stages["minimal_failure_stage"] = "case_schema" if errors or output is None else "none"
        return stages

    stages["minimal_failure_stage"] = "task_type"
    return stages


def _source_relationship_errors(output: StructuredAnalysisOutput) -> list[str]:
    requirement_ids = {item.requirement_id for item in output.requirements}
    return [
        test_item.test_item_id
        for test_item in output.test_items
        if not set(test_item.requirement_ids).issubset(requirement_ids)
    ]


def _redact_value(value: object, api_key: str) -> object:
    if isinstance(value, dict):
        return {
            str(key): _redact_value(item, api_key)
            for key, item in value.items()
            if not _SECRET_FIELD.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, api_key) for item in value]
    if isinstance(value, str):
        result = value.replace(api_key, "[REDACTED]") if api_key else value
        return _BEARER_VALUE.sub("Bearer [REDACTED]", result)
    return value
