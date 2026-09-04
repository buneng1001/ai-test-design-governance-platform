import json

from app.ai_service import AIModelConfig, ModelRequest, OpenAICompatibleModelService, _extract_structured_content, _finish_reason


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
