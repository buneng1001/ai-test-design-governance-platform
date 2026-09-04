import hashlib
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from dataclasses import dataclass
from typing import Protocol

from app.ai_schemas import AIModelConfig, AIOutputEnvelope, AITaskType, MockScenario
from app.review_schemas import StructuredAnalysisOutput


@dataclass(frozen=True)
class ModelRequest:
    task_type: AITaskType
    prompt_version: str
    model_parameters: AIModelConfig
    input_asset_versions: tuple[dict[str, int], ...]
    scenario: MockScenario
    input_context: tuple[dict[str, object], ...] = ()
    base_url: str = ""
    api_key: str = ""


@dataclass(frozen=True)
class ModelResponse:
    raw_output: object | None = None
    error_code: str | None = None
    retryable: bool = False
    diagnostic: str | None = None


MAX_MOCK_REQUIREMENTS = 100


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
            if request.task_type == "requirement_review" and request.input_context:
                return ModelResponse(raw_output={
                    "contract_version": "requirement-analysis.v1", "requirements": [],
                    "test_items": [], "acceptance_criteria": [], "findings": [],
                })
            return ModelResponse(raw_output={"contract_version": "ai-output.v1", "items": []})
        if request.task_type == "requirement_review" and request.input_context:
            return ModelResponse(raw_output=_mock_requirement_analysis(request))
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


class OpenAICompatibleModelService:
    """调用兼容 OpenAI Chat Completions 的服务，不保存 API Key。"""

    def complete(self, request: ModelRequest) -> ModelResponse:
        prompt = _prompt_for_request(request)
        response = _request_json(request, prompt, include_response_format=True)
        if response.error_code == "provider_http_400":
            # 部分 OpenAI 兼容服务不接受 response_format，降级为 Prompt 强制 JSON。
            response = _request_json(request, prompt, include_response_format=False)
        return response


def _request_json(request: ModelRequest, prompt: str, include_response_format: bool) -> ModelResponse:
    body_data: dict[str, object] = {
        "model": request.model_parameters.model,
        "temperature": request.model_parameters.temperature,
        "max_tokens": request.model_parameters.max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if include_response_format:
        body_data["response_format"] = {"type": "json_object"}
    body = json.dumps(body_data).encode("utf-8")
    http_request = Request(
        f"{request.base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {request.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(http_request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        finish_reason = _finish_reason(payload)
        if finish_reason == "length":
            return ModelResponse(
                error_code="provider_response_truncated",
                diagnostic="finish_reason=length",
            )
        return ModelResponse(raw_output=_extract_structured_content(payload))
    except HTTPError as error:
        retryable = error.code == 429 or error.code >= 500
        return ModelResponse(error_code=f"provider_http_{error.code}", retryable=retryable,
                             diagnostic=f"http_status={error.code}")
    except (URLError, TimeoutError) as error:
        return ModelResponse(error_code="provider_response_invalid", diagnostic=type(error).__name__)
    except (ValueError, KeyError, IndexError, TypeError) as error:
        return ModelResponse(error_code="provider_json_invalid", diagnostic=type(error).__name__)


def _finish_reason(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    reason = choices[0].get("finish_reason")
    return reason if isinstance(reason, str) else None


def _extract_structured_content(payload: object) -> object:
    """兼容常见 OpenAI 兼容服务的 JSON、代码块和多段文本响应。"""
    if not isinstance(payload, dict):
        raise ValueError("模型响应不是 JSON 对象")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("模型响应缺少 choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("模型响应缺少 message")
    content = message.get("content")
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    if not isinstance(content, str):
        raise ValueError("模型响应缺少可解析 content")
    text = content.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = text.removeprefix("```").removeprefix("json").removesuffix("```").strip()
    if not text.startswith(("{", "[")):
        start = min((index for index in (text.find("{"), text.find("[") ) if index >= 0), default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start >= 0 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


def validate_output(raw_output: object) -> tuple[dict | None, list[str]]:
    try:
        output = AIOutputEnvelope.model_validate(raw_output)
    except Exception as error:
        return None, [str(error)]
    return output.model_dump(mode="json"), []


def validate_requirement_analysis_output(raw_output: object) -> tuple[StructuredAnalysisOutput | None, list[str]]:
    try:
        return StructuredAnalysisOutput.model_validate(raw_output), []
    except Exception as error:
        return None, [str(error)]


def _mock_requirement_analysis(request: ModelRequest) -> dict[str, object]:
    requirements = []
    criteria = []
    test_items = []
    findings = []
    conflicts = []
    # Mock 结果必须先遵守需求分析契约上限，长文档不能生成超出契约的响应。
    bounded_context = request.input_context[:MAX_MOCK_REQUIREMENTS]
    for index, item in enumerate(bounded_context, start=1):
        source = item["source_reference"]
        source_reference = source if isinstance(source, dict) else {}
        requirement_id = f"REQ-CANDIDATE-{index}"
        requirements.append({
            "requirement_id": requirement_id,
            "name": f"需求 {index}",
            "statement": str(item["text"]),
            "requirement_type": "functional",
            "module": "未分类模块",
            "source_references": [source_reference],
            "analysis_note": "Mock 根据原始来源片段生成的确定性语义候选。",
        })
        test_items.append({
            "test_item_id": f"TEST-ITEM-{index}", "name": f"验证需求 {index}",
            "module": "未分类模块", "requirement_ids": [requirement_id],
            "source_references": [source_reference],
        })
        if any(marker in str(item["text"]) for marker in ("必须", "应当", "不得")):
            criterion_id = f"AC-{index}"
            criteria.append({"criterion_id": criterion_id, "statement": str(item["text"]),
                             "requirement_id": requirement_id, "source_references": [source_reference]})
            findings.append({
                "finding_id": f"FINDING-{index}", "finding_type": "missing_acceptance_criteria",
                "summary": "该约束需要明确可验证的验收标准",
                "reason": "Mock 识别到约束性表述，但不会替测试工程师补写验收标准。",
                "source_reference": source_reference,
            })
    for first, second in _conflict_pairs(bounded_context)[:MAX_MOCK_REQUIREMENTS]:
        conflict_id = "CONFLICT-" + hashlib.sha256(
            f"{first['text']}\n{second['text']}".encode("utf-8")
        ).hexdigest()[:12]
        conflicts.append({
            "conflict_id": conflict_id, "topic": "同一能力的资料描述不一致",
            "srs_text": str(first["text"]), "srs_source": first["source_reference"],
            "implementation_text": str(second["text"]), "implementation_source": second["source_reference"],
            "affected_modules": ["未分类模块"], "affected_test_items": ["TEST-ITEM-1"],
        })
    return {"contract_version": "requirement-analysis.v1", "requirements": requirements,
            "test_items": test_items, "acceptance_criteria": criteria, "findings": findings,
            "conflicts": conflicts}


def _prompt_for_request(request: ModelRequest) -> str:
    if request.task_type != "requirement_review":
        return (
            "请针对当前测试设计任务输出 ai-output.v1 JSON。只输出 contract_version 和 items，"
            "每项包含 candidate_id、summary、source_asset_ids。不得输出 Markdown 或 API Key。"
        )
    return _requirement_prompt(request)


def _requirement_prompt(request: ModelRequest) -> str:
    context = json.dumps(request.input_context, ensure_ascii=False)
    return ("请分析以下多文件需求资料，严格只输出紧凑的 requirement-analysis.v1 JSON，不要输出 Markdown、解释文字或思考过程。"
            "归并同义内容，提取需求、模块、"
            "测试项、验收条件，并识别歧义、遗漏、冲突、不可测试条件。每条语义结果必须引用输入中的完整"
            "source_reference，不得凭空创造来源。原始资料：" + context)


def _conflict_pairs(context: tuple[dict[str, object], ...]) -> list[tuple[dict[str, object], dict[str, object]]]:
    pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    for index, first in enumerate(context):
        first_source = first.get("source_reference", {})
        first_filename = first_source.get("filename") if isinstance(first_source, dict) else None
        first_tokens = _conflict_tokens(str(first.get("text", "")))
        for second in context[index + 1:]:
            second_source = second.get("source_reference", {})
            second_filename = second_source.get("filename") if isinstance(second_source, dict) else None
            if not first_filename or first_filename == second_filename:
                continue
            second_tokens = _conflict_tokens(str(second.get("text", "")))
            single_fragment_files = _single_fragment_files(context)
            related = len(first_tokens & second_tokens) >= 2 or (
                first_filename in single_fragment_files and second_filename in single_fragment_files
            )
            if related and first.get("text") != second.get("text"):
                pairs.append((first, second))
    return pairs


def _conflict_tokens(text: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2}", text))
    return words


def _single_fragment_files(context: tuple[dict[str, object], ...]) -> set[str]:
    counts: dict[str, int] = {}
    for item in context:
        source = item.get("source_reference", {})
        filename = source.get("filename") if isinstance(source, dict) else None
        if filename:
            counts[filename] = counts.get(filename, 0) + 1
    return {filename for filename, count in counts.items() if count == 1}
