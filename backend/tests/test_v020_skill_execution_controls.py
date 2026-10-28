from types import SimpleNamespace

import pytest

from app.ai_service import ModelResponse
from app.v020_model_errors import V020RunError
from app.v020_run_schemas import AnalysisModelOutput
from app.v020_skill_batching import SkillStageBatch, stage_batch
from app.v020_skill_contracts import (
    MODEL_STAGES, SKILL_RETRY_BACKOFF_SECONDS, SKILL_STAGE_OUTPUT_TOKENS, skill_preflight_prompts,
)
from app.v020_skill_model_runner import SkillModelRunner
from app.v020_skill_validation import validate_merged_stage, validate_stage


class MemoryRepository:
    def __init__(self, run: dict) -> None:
        self.run = run

    def get_run(self, _project_id: int, _run_id: str) -> dict:
        return self.run

    def update_run(self, run: dict) -> None:
        self.run = run


class SequenceModelService:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def complete(self, _request) -> ModelResponse:
        self.calls += 1
        return self.responses.pop(0)


def _runner(service, run: dict) -> SkillModelRunner:
    return SkillModelRunner(
        service,
        MemoryRepository(run),
        SimpleNamespace(
            provider="custom", model="test-model", base_url="https://example.invalid/v1",
            api_key="secret", network_mode="direct",
        ),
        run,
        {"provider": "custom", "model": "test-model"},
    )


def _batch() -> SkillStageBatch:
    return SkillStageBatch(("input-1",), {"fragments": []}, {})


def test_model_runner_never_exceeds_the_confirmed_hard_request_limit() -> None:
    run = {
        "id": "run-1", "project_id": 1, "attempts": [{"attempt": 1}],
        "max_request_count": 1, "cancel_requested": False,
    }
    service = SequenceModelService([ModelResponse(raw_output={})])

    with pytest.raises(V020RunError, match="1 次模型调用硬上限"):
        _runner(service, run).call(MODEL_STAGES[0], 1, _batch(), "prompt")

    assert service.calls == 0
    assert len(run["attempts"]) == 1


def test_retryable_failure_waits_with_bounded_backoff(monkeypatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr("app.v020_skill_model_runner.sleep", waits.append)
    run = {
        "id": "run-2", "project_id": 1, "attempts": [],
        "max_request_count": 10, "cancel_requested": False,
    }
    service = SequenceModelService([
        ModelResponse(error_code="provider_timeout", retryable=True),
        ModelResponse(raw_output={}),
    ])

    response = _runner(service, run).call(MODEL_STAGES[0], 1, _batch(), "prompt")

    assert response.error_code is None
    assert service.calls == 2
    assert sum(waits) == pytest.approx(SKILL_RETRY_BACKOFF_SECONDS)
    assert max(waits) <= 0.1


def test_stage_batch_preserves_cross_requirement_function_and_rule_links() -> None:
    context = {"fragments": [
        {"source_reference_id": "input-1", "text": "需求一"},
        {"source_reference_id": "input-2", "text": "需求二"},
    ]}
    artifacts = {
        "S00": {
            "atomic_requirements": [
                {"requirement_id": "REQ-1", "statement": "需求一", "source_reference_id": "input-1"},
                {"requirement_id": "REQ-2", "statement": "需求二", "source_reference_id": "input-2"},
            ],
            "source_coverage": [
                {"source_reference_id": "input-1", "requirement_ids": ["REQ-1"], "no_requirement_reason": ""},
                {"source_reference_id": "input-2", "requirement_ids": ["REQ-2"], "no_requirement_reason": ""},
            ],
            "questions": [],
        },
        "S01": {"functions": [{
            "function_id": "FUN-1", "module": "状态", "name": "切换", "description": "组合状态切换",
            "requirement_ids": ["REQ-1", "REQ-2"],
        }]},
        "S02": {"rules": [{
            "rule_id": "RULE-1", "description": "两项需求共同约束状态切换",
            "requirement_ids": ["REQ-1", "REQ-2"],
        }]},
    }

    batch = stage_batch(MODEL_STAGES[3], context, artifacts, ("REQ-1",))

    assert batch.scope_ids == ("REQ-1",)
    assert batch.artifacts["S01"]["functions"][0]["requirement_ids"] == ["REQ-1", "REQ-2"]
    assert batch.artifacts["S02"]["rules"][0]["requirement_ids"] == ["REQ-1", "REQ-2"]


def test_function_stage_can_discover_relationships_from_the_global_requirement_index() -> None:
    context, artifacts = _relationship_context()
    batch = stage_batch(MODEL_STAGES[1], context, artifacts, ("REQ-1",))
    raw = {"functions": [{
        "function_id": "FUN-1", "module": "状态", "name": "切换", "description": "组合状态切换",
        "requirement_ids": ["REQ-1", "REQ-2"],
    }]}

    output = validate_stage(MODEL_STAGES[1], raw, batch.context, batch.artifacts)

    assert output["functions"][0]["requirement_ids"] == ["REQ-1", "REQ-2"]


def test_preflight_splits_a_prompt_that_only_exceeds_the_limit_as_a_multi_item_batch() -> None:
    context = {
        "test_object": "终端", "software_version": "v1", "supplemental_notes": "",
        "fragments": [{
            "source_reference_id": f"input-{index}", "text": "需求" * 3_000,
        } for index in range(1, 5)],
    }

    prompts = skill_preflight_prompts(context)

    assert len(prompts) > 7
    assert all(_estimate_tokens(prompt) + SKILL_STAGE_OUTPUT_TOKENS <= 32_000 for prompt in prompts)


def test_merged_stage_and_final_analysis_accept_more_than_the_single_batch_row_limit() -> None:
    context = {"fragments": [{"source_reference_id": "input-1"}]}
    artifacts = {"S00": {"atomic_requirements": [{
        "requirement_id": "REQ-1", "statement": "需求", "source_reference_id": "input-1",
    }]}}
    row = {
        "module": "状态", "test_item": "状态切换", "test_basis": "需求依据",
        "source_reference_id": "input-1", "test_type": "功能测试", "priority": "P1",
        "related_requirement_id": "REQ-1",
    }
    raw = {"rows": [dict(row) for _ in range(501)]}

    merged = validate_merged_stage(MODEL_STAGES[3], raw, context, artifacts)
    final = AnalysisModelOutput.model_validate(merged)

    assert len(final.rows) == 501


def _relationship_context() -> tuple[dict, dict]:
    context = {"fragments": [
        {"source_reference_id": "input-1", "text": "需求一"},
        {"source_reference_id": "input-2", "text": "需求二"},
    ]}
    artifacts = {"S00": {
        "atomic_requirements": [
            {"requirement_id": "REQ-1", "statement": "需求一", "source_reference_id": "input-1"},
            {"requirement_id": "REQ-2", "statement": "需求二", "source_reference_id": "input-2"},
        ],
        "source_coverage": [
            {"source_reference_id": "input-1", "requirement_ids": ["REQ-1"], "no_requirement_reason": ""},
            {"source_reference_id": "input-2", "requirement_ids": ["REQ-2"], "no_requirement_reason": ""},
        ],
        "questions": [],
    }}
    return context, artifacts


def _estimate_tokens(value: str) -> int:
    non_ascii = sum(1 for character in value if ord(character) > 127)
    return max(1, non_ascii + (len(value) - non_ascii + 3) // 4)
