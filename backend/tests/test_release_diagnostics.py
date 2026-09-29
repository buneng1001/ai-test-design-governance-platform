import json

from app.ai_schemas import AIModelConfig
from app.ai_service import ModelRequest, ModelResponse
from app.release_diagnostics import record_real_model_failure, replay_release_diagnostic


def test_local_failure_diagnostic_is_redacted_bounded_and_replayable(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RC2_LOCAL_DIAGNOSTIC_DIR", str(tmp_path / ".ticket11-release-diagnostics"))
    api_key = "test-secret-key"
    request = ModelRequest(
        task_type="requirement_review", prompt_version="test", model_parameters=AIModelConfig(
            provider="deepseek", model="deepseek-v4-flash"
        ), input_asset_versions=(), scenario="normal", input_context=(),
        base_url="https://api.example.test", api_key=api_key,
    )
    provider_response = {
        "api_key": api_key,
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "contract_version": "requirement-analysis.v1", "requirements": [{"requirement_id": "R-1"}],
            "test_items": [], "acceptance_criteria": [], "findings": [], "conflicts": [],
        })}}],
    }
    diagnostic_path = record_real_model_failure(
        request, "requirement_schema", ModelResponse(
            raw_output={"requirements": [{"requirement_id": "R-1"}]}, provider_response=provider_response,
            http_status=200, finish_reason="stop", response_length=321,
        ), [f"secret={api_key}"] + [f"error-{index}" for index in range(11)],
    )

    assert diagnostic_path is not None
    serialized = diagnostic_path.read_text(encoding="utf-8")
    assert api_key not in serialized
    diagnostic = json.loads(serialized)
    assert diagnostic["provider"] == "deepseek"
    assert diagnostic["failure_stage"] == "requirement_schema"
    assert diagnostic["http_status"] == 200 and diagnostic["finish_reason"] == "stop"
    assert diagnostic["response_length"] == 321 and len(diagnostic["schema_errors"]) == 10
    replay = replay_release_diagnostic(diagnostic_path)
    assert replay["json_extraction"] == "passed"
    assert replay["requirement_schema"] == "failed"
    assert replay["source_relationships"] == "not_run"


def test_local_failure_diagnostic_rejects_non_ignored_destination(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RC2_LOCAL_DIAGNOSTIC_DIR", str(tmp_path / "diagnostics"))
    request = ModelRequest(
        task_type="requirement_review", prompt_version="test",
        model_parameters=AIModelConfig(provider="deepseek", model="deepseek-v4-flash"),
        input_asset_versions=(), scenario="normal", base_url="https://api.example.test", api_key="test-secret-key",
    )

    assert record_real_model_failure(request, "model_call", ModelResponse(error_code="provider_timeout")) is None
