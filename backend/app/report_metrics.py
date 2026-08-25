from typing import TypeAlias

from app.evaluation_schemas import EvaluationRun


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
ReportPayload: TypeAlias = dict[str, JsonValue]


def review_counts(reviews: list[object]) -> ReportPayload:
    return {
        "analysis_count": len(reviews),
        "atomic_requirement_count": sum(len(item.atomic_requirements) for item in reviews),
        "accepted_requirement_count": sum(
            sum(candidate.decision == "accepted" for candidate in item.atomic_requirements) for item in reviews
        ),
        "finding_count": sum(len(item.findings) for item in reviews),
        "visual_inference_count": sum(len(item.visual_inferences) for item in reviews),
    }


def source_references(reviews: list[object], designs: list[object]) -> list[JsonValue]:
    references: list[JsonValue] = []
    for item in [*reviews, *designs]:
        for reference in walk_references(item.model_dump(mode="json")):
            if reference not in references:
                references.append(reference)
    return references


def ai_summary(run: object) -> ReportPayload:
    return {
        "id": run.id,
        "task_type": run.task_type,
        "prompt_version": run.prompt_version,
        "input_asset_versions": run.input_asset_versions,
        "validation_status": run.validation_status,
        "status": run.status,
        "is_mock": run.is_mock,
        "attempts": [item.model_dump(mode="json") for item in run.attempts],
        "dispositions": run.dispositions,
    }


def ai_effectiveness(runs: list[object], evaluation: EvaluationRun | None = None) -> ReportPayload:
    total = len(runs)
    passed = sum(run.validation_status == "passed" for run in runs)
    source_total = 0
    valid_sources = 0
    for run in runs:
        output_items = (run.output or {}).get("items", [])
        allowed_assets = {item["asset_id"] for item in run.input_asset_versions}
        for item in output_items:
            source_total += len(item.get("source_asset_ids", []))
            valid_sources += sum(asset_id in allowed_assets for asset_id in item.get("source_asset_ids", []))
    dispositions = [item for run in runs for item in run.dispositions]
    adopted = sum(item.get("decision") in {"accepted", "modified"} for item in dispositions)
    metrics: ReportPayload = {
        "structural_compliance_rate": {"numerator": passed, "denominator": total, "percentage": rate(passed, total)},
        "source_reference_validity_rate": {
            "numerator": valid_sources,
            "denominator": source_total,
            "percentage": rate(valid_sources, source_total),
        },
        "truth_hit": {
            "matched": None,
            "total": None,
            "status": "not_evaluated",
            "reason": "评估真值与正常模型上下文隔离，当前报告不读取真值原文",
        },
        "key_omissions": {
            "count": None,
            "status": "not_evaluated",
            "reason": "需要独立评估运行，不能从普通 AI 运行推断",
        },
        "unsupported_expansions": {
            "count": None,
            "status": "not_evaluated",
            "reason": "需要独立评估运行，不能从普通 AI 运行推断",
        },
        "human_adoption_rate": {
            "numerator": adopted,
            "denominator": len(dispositions),
            "percentage": rate(adopted, len(dispositions)),
        },
    }
    if evaluation is not None:
        evaluated = evaluation.metrics.model_dump(mode="json")
        metrics.update({
            "truth_hit": evaluated["truth_hit"],
            "key_omissions": evaluated["key_omissions"],
            "unsupported_expansions": evaluated["unsupported_expansions"],
            "distractor_hits": evaluated["distractor_hits"],
            "evaluation_run_id": evaluation.id,
            "evaluation_input_sha256": evaluation.input_sha256,
        })
    return metrics


def version_summary(version: object) -> ReportPayload:
    return {
        "id": version.id,
        "package_id": version.package_id,
        "version": version.version,
        "name": version.name,
        "materials": [
            {
                "asset_id": item.asset_id,
                "asset_revision": item.asset_revision,
                "filename": item.filename,
                "format": item.format,
                "sha256": item.sha256,
                "parse_status": item.parse_status,
                "diagnostics": [diagnostic.model_dump(mode="json") for diagnostic in item.diagnostics],
            }
            for item in version.materials
        ],
        "diagnostics": [item.model_dump(mode="json") for item in version.diagnostics],
    }


def walk_references(value: object) -> list[ReportPayload]:
    if isinstance(value, dict):
        if {"asset_id", "filename", "locator"}.issubset(value):
            return [value]
        return [item for child in value.values() for item in walk_references(child)]
    if isinstance(value, list):
        return [item for child in value for item in walk_references(child)]
    return []


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 100.0
