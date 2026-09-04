import json

from app.ai_service import (
    AIModelConfig, ModelRequest, OpenAICompatibleModelService, _extract_structured_content, _finish_reason,
    _provider_request_parameters, validate_requirement_analysis_output,
)


def test_extract_structured_content_accepts_common_provider_response_formats() -> None:
    expected = {"contract_version": "requirement-analysis.v1", "requirements": []}

    assert _extract_structured_content({"choices": [{"message": {"content": json.dumps(expected)}}]}) == expected
    assert _extract_structured_content({"choices": [{"message": {"content": f"```json\n{json.dumps(expected)}\n```"}}]}) == expected
    assert _extract_structured_content({"choices": [{"message": {"content": expected}}]}) == expected
    assert _extract_structured_content({"choices": [{"message": {"content": [{"text": json.dumps(expected)}]}}]}) == expected
    assert _extract_structured_content({
        "choices": [{"message": {"content": f"<think>分析需求</think>\n{json.dumps(expected)}"}}],
    }) == expected
    assert _extract_structured_content({
        "choices": [{"message": {"content": None, "reasoning_content": json.dumps(expected)}}],
    }) == expected


def test_finish_reason_identifies_truncated_provider_output() -> None:
    assert _finish_reason({"choices": [{"finish_reason": "length"}]}) == "length"
    assert _finish_reason({"choices": [{"finish_reason": "stop"}]}) == "stop"
    assert _finish_reason({"choices": []}) is None


def test_timeout_is_retryable_and_not_reported_as_json_error(monkeypatch) -> None:
    def timeout(*_args, **_kwargs):
        raise TimeoutError("provider timed out")

    monkeypatch.setattr("app.ai_service.urlopen", timeout)
    response = OpenAICompatibleModelService().complete(ModelRequest(
        task_type="requirement_review", prompt_version="test",
        model_parameters=AIModelConfig(provider="test", model="m"), input_asset_versions=(),
        scenario="normal", input_context=(), base_url="https://example.com", api_key="key",
    ))
    assert response.error_code == "provider_timeout"
    assert response.retryable is True


def test_provider_thinking_parameters_are_disabled_for_structured_analysis() -> None:
    assert _provider_request_parameters("deepseek", "deepseek-v4-flash") == {
        "thinking": {"type": "disabled"},
    }
    assert _provider_request_parameters("siliconflow", "deepseek-ai/DeepSeek-V3.2") == {
        "enable_thinking": False,
    }


def test_requirement_output_normalizes_existing_string_source_references() -> None:
    context = ({"source_reference": {
        "reference_id": "ref-1", "asset_id": 7, "filename": "SRS.md", "locator": "line 1",
    }},)
    output, errors = validate_requirement_analysis_output({
        "requirements": [{
            "requirement_id": "REQ-1", "name": "需求", "statement": "系统应工作",
            "requirement_type": "functional", "module": "核心", "source_references": ["SRS.md"],
            "analysis_note": "来源可追溯",
        }], "test_items": [], "acceptance_criteria": [], "findings": [], "conflicts": [],
    }, context)
    assert not errors
    assert output is not None
    assert output.contract_version == "requirement-analysis.v1"
    assert output.requirements[0].source_references[0].reference_id == "ref-1"
