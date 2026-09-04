import json

from app.ai_service import (
    AIModelConfig, ModelRequest, OpenAICompatibleModelService, _extract_structured_content, _finish_reason,
    _provider_request_parameters, _requirement_input_statistics, _requirement_prompt, analysis_max_tokens,
    validate_requirement_analysis_output,
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


def test_connection_error_is_reported_as_provider_connection_error(monkeypatch) -> None:
    def connection_error(*_args, **_kwargs):
        raise ConnectionResetError("connection reset")

    monkeypatch.setattr("app.ai_service.urlopen", connection_error)
    response = OpenAICompatibleModelService().complete(ModelRequest(
        task_type="requirement_review", prompt_version="test",
        model_parameters=AIModelConfig(provider="test", model="m"), input_asset_versions=(),
        scenario="normal", input_context=(), base_url="https://example.com", api_key="key",
    ))
    assert response.error_code == "provider_connection_error"
    assert response.retryable is True


def test_provider_thinking_parameters_are_disabled_for_structured_analysis() -> None:
    assert _provider_request_parameters("deepseek", "deepseek-v4-flash") == {
        "thinking": {"type": "disabled"},
    }
    assert _provider_request_parameters("siliconflow", "deepseek-ai/DeepSeek-V3.2") == {
        "enable_thinking": False,
    }


def test_requirement_analysis_reserves_large_output_budget() -> None:
    assert analysis_max_tokens("deepseek", "deepseek-v4-flash") == 10000
    assert analysis_max_tokens("siliconflow", "Qwen/Qwen2.5-72B-Instruct") == 10000


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


def test_requirement_output_allows_unmapped_optional_finding_source() -> None:
    output, errors = validate_requirement_analysis_output({
        "requirements": [], "test_items": [], "acceptance_criteria": [],
        "findings": [{
            "finding_id": "F-1", "finding_type": "ambiguity", "summary": "存在歧义",
            "reason": "需要人工确认", "source_reference": "未提供来源",
        }], "conflicts": [],
    })
    assert not errors
    assert output is not None
    assert output.findings[0].source_reference is None


def test_requirement_prompt_reports_input_statistics_without_small_fixed_limits() -> None:
    context = tuple({
        "text": f"FR-{index:03d}：系统应支持第 {index} 项能力。",
        "source_reference": {
            "reference_id": f"ref-{index}", "asset_id": index, "filename": "SRS-rc.2-v2.md",
            "locator": f"line {index}",
        },
    } for index in range(1, 49))
    request = ModelRequest(
        task_type="requirement_review", prompt_version="test",
        model_parameters=AIModelConfig(provider="test", model="m"), input_asset_versions=(),
        scenario="normal", input_context=context, base_url="", api_key="",
    )

    prompt = _requirement_prompt(request)
    assert "来源片段 48 个" in prompt
    assert "需求编号 48 个" in prompt
    assert "最多输出 12 条" not in prompt
    assert "[S1] FR-001：系统应支持第 1 项能力。" in prompt
    assert '"reference_id": "ref-1"' not in prompt


def test_requirement_output_resolves_compact_source_aliases() -> None:
    context = tuple({
        "text": f"FR-{index}：需求内容。",
        "source_reference": {
            "reference_id": f"ref-{index}", "asset_id": 7, "filename": "SRS.md",
            "locator": f"line {index}",
        },
    } for index in range(1, 3))
    output, errors = validate_requirement_analysis_output({
        "requirements": [{
            "requirement_id": "REQ-1", "name": "需求", "statement": "系统应工作",
            "requirement_type": "functional", "module": "核心", "source_references": ["S2"],
            "analysis_note": "来源可追溯",
        }], "test_items": [], "acceptance_criteria": [], "findings": [], "conflicts": [],
    }, context)
    assert not errors
    assert output is not None
    assert output.requirements[0].source_references[0].reference_id == "ref-2"


def test_requirement_output_normalizes_type_alias_and_empty_analysis_note() -> None:
    context = ({"source_reference": {
        "reference_id": "ref-1", "asset_id": 7, "filename": "SRS.md", "locator": "line 1",
    }},)
    output, errors = validate_requirement_analysis_output({
        "requirements": [{
            "requirement_id": "REQ-1", "name": "需求", "statement": "系统应工作",
            "requirement_type": "业务功能", "module": "核心", "source_references": ["S1"],
            "analysis_note": "",
        }], "test_items": [], "acceptance_criteria": [], "findings": [], "conflicts": [],
    }, context)
    assert not errors
    assert output is not None
    assert output.requirements[0].requirement_type == "functional"
    assert output.requirements[0].analysis_note == "模型未提供补充分析说明。"
