import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from app.ai_schemas import AIModelConfig, AIOutputEnvelope, AITaskType, MockScenario


@dataclass(frozen=True)
class ModelRequest:
    task_type: AITaskType
    prompt_version: str
    model_parameters: AIModelConfig
    input_asset_versions: tuple[dict[str, int], ...]
    scenario: MockScenario


@dataclass(frozen=True)
class ModelResponse:
    raw_output: object | None = None
    error_code: str | None = None
    retryable: bool = False


class ModelService(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse:
        """模型服务只返回平台边界内的结果，不暴露提供方响应结构。"""


class MockModelService:
    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.scenario == "timeout":
            return ModelResponse(error_code="timeout", retryable=True)
        if request.scenario == "rate_limit":
            return ModelResponse(error_code="rate_limit", retryable=True)
        if request.scenario == "temporary_error":
            return ModelResponse(error_code="temporary_error", retryable=True)
        if request.scenario in {"authentication_error", "parameter_error", "content_safety_error"}:
            return ModelResponse(error_code=request.scenario, retryable=False)
        if request.scenario == "invalid_schema":
            return ModelResponse(raw_output={"contract_version": "ai-output.v1", "unexpected": True})
        if request.scenario == "missing_source":
            return ModelResponse(
                raw_output={
                    "contract_version": "ai-output.v1",
                    "items": [{"candidate_id": "candidate-1", "summary": "缺少来源的候选", "source_asset_ids": []}],
                }
            )
        if request.scenario == "empty":
            return ModelResponse(raw_output={"contract_version": "ai-output.v1", "items": []})
        seed = json.dumps(
            {
                "task_type": request.task_type,
                "prompt_version": request.prompt_version,
                "input_asset_versions": request.input_asset_versions,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        candidate_id = f"mock-{hashlib.sha256(seed).hexdigest()[:12]}"
        return ModelResponse(
            raw_output={
                "contract_version": "ai-output.v1",
                "items": [
                    {
                        "candidate_id": candidate_id,
                        "summary": f"Mock 对 {request.task_type} 的确定性候选",
                        "source_asset_ids": [item["asset_id"] for item in request.input_asset_versions],
                    }
                ],
            }
        )


class UnavailableModelService:
    def complete(self, request: ModelRequest) -> ModelResponse:
        """真实服务尚未配置时只返回边界错误，不把提供方响应带入领域模型。"""
        return ModelResponse(error_code="provider_unavailable", retryable=False)


def validate_output(raw_output: object) -> tuple[dict | None, list[str]]:
    try:
        output = AIOutputEnvelope.model_validate(raw_output)
    except Exception as error:
        return None, [str(error)]
    return output.model_dump(mode="json"), []
