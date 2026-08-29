import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from app.ai_repository import AIRunRepository
from app.asset_repository import AssetRepository
from app.evaluation_repository import EvaluationRepository
from app.evaluation_schemas import (
    EvaluationMetric,
    EvaluationMetrics,
    EvaluationRun,
    EvaluationRunInput,
    EvaluationTruthItem,
)


def create_evaluation(project_id: int, data: EvaluationRunInput, assets: AssetRepository,
                      ai_runs: AIRunRepository, evaluations: EvaluationRepository) -> EvaluationRun:
    truth_asset = assets.get(project_id, data.truth_asset_id)
    if truth_asset is None:
        raise ValueError("评估真值资产不存在")
    if truth_asset.asset_type != "evaluation_truth":
        raise ValueError("评估运行只能使用评估真值资产")
    if truth_asset.can_enter_model_context:
        raise ValueError("评估真值不能进入普通模型上下文")
    truth_items, distractors = _load_truth(assets.content(project_id, truth_asset.id))
    runs = []
    for run_id in sorted(set(data.ai_run_ids)):
        run = ai_runs.get(project_id, run_id)
        if run is None:
            raise ValueError("评估引用的 AI 运行不存在")
        runs.append(run)
    outputs = [
        (run, item)
        for run in runs
        if run.output and isinstance(run.output.get("items"), list)
        for item in run.output["items"]
        if isinstance(item, dict) and isinstance(item.get("summary"), str)
    ]
    matched_truth = [item for item in truth_items if any(_matches(item, output["summary"]) for _, output in outputs)]
    matched_output_ids = {
        output["candidate_id"] for _, output in outputs
        if any(_matches(item, output["summary"]) for item in truth_items)
    }
    distractor_hits = [
        distractor for distractor in distractors
        if any(_contains(distractor, output["summary"]) for _, output in outputs)
    ]
    unsupported_outputs = [
        output["candidate_id"] for run, output in outputs
        if _is_unsupported(run, output, distractors)
    ]
    metrics = EvaluationMetrics(
        truth_hit=_metric(len(matched_truth), len(truth_items)),
        key_omissions=_metric(len(truth_items) - len(matched_truth), len(truth_items)),
        unsupported_expansions=_metric(len(unsupported_outputs), len(outputs)),
        distractor_hits=_metric(len(distractor_hits), len(distractors)),
        output_item_count=len(outputs),
        matched_output_item_count=len(matched_output_ids),
    )
    input_sha256 = hashlib.sha256(
        json.dumps(
            {"truth_items": [item.model_dump() for item in truth_items], "distractors": distractors},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    evaluation = EvaluationRun(
        id=0, project_id=project_id, truth_asset_id=truth_asset.id,
        truth_sha256=truth_asset.sha256, input_sha256=input_sha256,
        ai_run_ids=sorted(set(data.ai_run_ids)), metrics=metrics,
        unmatched_output_candidate_ids=unsupported_outputs, created_at=datetime.now(UTC),
    )
    return evaluations.create(evaluation)


def _load_truth(encoded: str | None) -> tuple[list[EvaluationTruthItem], list[str]]:
    if not encoded:
        raise ValueError("评估真值资产内容不可用")
    try:
        document = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("评估真值资产不是有效的 UTF-8 JSON") from error
    if not isinstance(document, dict) or document.get("contract_version") != "evaluation-truth.v1":
        raise ValueError("评估真值资产契约版本无效")
    if isinstance(document.get("items"), list):
        items = [EvaluationTruthItem.model_validate(item) for item in document["items"]]
    else:
        items = _parse_synthetic_truth(document)
    if not items or len({item.truth_id for item in items}) != len(items):
        raise ValueError("评估真值必须包含唯一的真值项")
    return items, _parse_distractors(document.get("distractors", []))


def _parse_synthetic_truth(document: dict[str, Any]) -> list[EvaluationTruthItem]:
    items: list[EvaluationTruthItem] = []
    for finding in document.get("review_findings", []):
        items.append(_truth_item(finding, "review_finding", finding.get("key"), finding.get("id")))
    for index, key in enumerate(document.get("key_scope", []), start=1):
        items.append(_truth_item({}, "key_scope", key, f"KEY-{index:03d}"))
    for risk in document.get("risks", []):
        items.append(_truth_item(risk, "risk", risk.get("risk"), risk.get("id")))
    for impact in document.get("v2_impacts", []):
        items.append(_truth_item(impact, "change_impact", impact.get("change_id"), impact.get("change_id")))
    return items


def _truth_item(source: dict[str, Any], category: str, key: Any, truth_id: Any) -> EvaluationTruthItem:
    if not isinstance(key, str) or not isinstance(truth_id, str):
        raise ValueError("评估真值项缺少 key 或 truth_id")
    aliases = source.get("match_terms", [])
    if category == "change_impact":
        aliases = [*aliases, *source.get("expected_assets", [])]
    return EvaluationTruthItem(
        truth_id=truth_id, category=category, key=key,
        match_terms=[term for term in aliases if isinstance(term, str)],
    )


def _parse_distractors(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("评估干扰项格式无效")
    result = [value if isinstance(value, str) else value.get("text") for value in values]
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError("评估干扰项缺少文本")
    return result


def _matches(item: EvaluationTruthItem, summary: str) -> bool:
    normalized_summary = _normalize(summary)
    normalized_key = _normalize(item.key)
    normalized_terms = [_normalize(term) for term in item.match_terms]
    return normalized_key in normalized_summary or bool(normalized_terms) and all(
        term in normalized_summary for term in normalized_terms
    )


def _is_unsupported(run: Any, output: dict[str, Any], distractors: list[str]) -> bool:
    source_ids = set(output.get("source_asset_ids", []))
    input_ids = {item.get("asset_id") for item in run.input_asset_versions}
    return bool(source_ids - input_ids) or any(_contains(text, output["summary"]) for text in distractors)


def _contains(text: str, summary: str) -> bool:
    return _normalize(text) in _normalize(summary)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _metric(numerator: int, denominator: int) -> EvaluationMetric:
    percentage = round(numerator / denominator * 100, 2) if denominator else 0.0
    return EvaluationMetric(numerator=numerator, denominator=denominator, percentage=percentage)
