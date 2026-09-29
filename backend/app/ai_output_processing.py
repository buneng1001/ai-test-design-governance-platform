"""模型输出的本地结构修复、契约校验与保守归一化。"""

from __future__ import annotations

from pydantic import ValidationError

from app.ai_schemas import AIOutputEnvelope
from app.review_schemas import StructuredAnalysisOutput


def validate_output(raw_output: object) -> tuple[dict | None, list[str]]:
    try:
        output = AIOutputEnvelope.model_validate(raw_output)
    except Exception as error:
        return None, [str(error)]
    return output.model_dump(mode="json"), []


def local_structural_repair(raw_output: object) -> object:
    """只清理包装层和未知字段，绝不补写业务语义。"""
    if not isinstance(raw_output, dict):
        return raw_output
    if "items" in raw_output:
        return {key: raw_output[key] for key in ("contract_version", "items") if key in raw_output}
    known = {"contract_version", "requirements", "test_items", "acceptance_criteria", "findings", "conflicts"}
    return {key: value for key, value in raw_output.items() if key in known}


def validate_requirement_analysis_output(
    raw_output: object, input_context: tuple[dict[str, object], ...] = ()
) -> tuple[StructuredAnalysisOutput | None, list[str]]:
    try:
        normalized = _normalize_requirement_output(raw_output, input_context)
        return StructuredAnalysisOutput.model_validate(normalized), []
    except ValidationError as error:
        return None, [
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()[:10]
        ]


def _normalize_requirement_output(raw_output: object, input_context: tuple[dict[str, object], ...]) -> object:
    if not isinstance(raw_output, dict):
        return raw_output
    normalized = dict(raw_output)
    normalized.setdefault("contract_version", "requirement-analysis.v1")
    references = [
        item.get("source_reference") for item in input_context
        if isinstance(item.get("source_reference"), dict)
    ]
    for collection_name in ("requirements", "test_items", "acceptance_criteria", "findings"):
        collection = normalized.get(collection_name)
        if isinstance(collection, list):
            normalized[collection_name] = [
                _normalize_output_item(
                    item, references, optional_finding_source=collection_name == "findings",
                )
                for item in collection
            ]
    conflicts = normalized.get("conflicts")
    if isinstance(conflicts, list):
        normalized["conflicts"] = [_normalize_output_item(item, references) for item in conflicts]
    return normalized


def _normalize_output_item(
    item: object, references: list[object], optional_finding_source: bool = False,
) -> object:
    if not isinstance(item, dict):
        return item
    normalized = dict(item)
    if "requirement_type" in normalized:
        normalized["requirement_type"] = _normalize_requirement_type(normalized["requirement_type"])
    if "finding_type" in normalized:
        normalized["finding_type"] = _normalize_finding_type(normalized["finding_type"])
    if "analysis_note" in normalized and not str(normalized["analysis_note"]).strip():
        normalized["analysis_note"] = "模型未提供补充分析说明。"
    for field in ("source_references", "source_reference", "srs_source", "implementation_source"):
        if field in normalized:
            value = normalized[field]
            if field == "source_references" and isinstance(value, list):
                normalized[field] = [
                    _resolve_source_reference(item, references, index)
                    for index, item in enumerate(value)
                ]
            else:
                resolved = _resolve_source_reference(value, references)
                normalized[field] = None if optional_finding_source and resolved is value else resolved
    return normalized


def _normalize_requirement_type(value: object) -> str:
    """把常见中文分类归一到平台契约，避免单个分类词使整批结果失效。"""
    if isinstance(value, str):
        normalized = value.strip().lower()
        aliases = {
            "功能": "functional", "功能性": "functional", "业务功能": "functional",
            "接口": "interface", "接口类": "interface", "数据": "data", "数据类": "data",
            "质量": "quality", "非功能": "quality", "约束": "constraint", "限制": "constraint",
            "流程": "workflow", "工作流": "workflow",
        }
        allowed = {"functional", "interface", "data", "quality", "constraint", "workflow", "other"}
        return aliases.get(normalized, normalized if normalized in allowed else "other")
    return "other"


def _normalize_finding_type(value: object) -> str:
    """兼容真实模型常用中文发现分类，仍只输出既有契约枚举。"""
    if not isinstance(value, str):
        return "other"
    normalized = value.strip().lower()
    aliases = {
        "歧义": "ambiguity", "遗漏": "omission", "冲突": "conflict", "不可测试": "untestable",
        "缺少验收标准": "missing_acceptance_criteria", "依赖不清": "dependency_unclear",
        "缺少约束或异常处理": "missing_constraint_or_error_handling", "视觉推断待确认": "visual_inference_pending",
    }
    allowed = {
        "ambiguity", "omission", "conflict", "untestable", "missing_acceptance_criteria", "dependency_unclear",
        "missing_constraint_or_error_handling", "visual_inference_pending", "other",
    }
    return aliases.get(normalized, normalized if normalized in allowed else "other")


def _resolve_source_reference(value: object, references: list[object], field_index: int | None = None) -> object:
    if isinstance(value, dict) and {"reference_id", "asset_id", "filename", "locator"}.issubset(value):
        return value
    text = str(value).strip() if isinstance(value, (str, int)) else ""
    if not text:
        return value
    if text.startswith("S") and text[1:].isdigit():
        reference_index = int(text[1:]) - 1
        if 0 <= reference_index < len(references):
            return references[reference_index]
    for reference in references:
        if not isinstance(reference, dict):
            continue
        candidates = (reference.get("reference_id"), reference.get("filename"), reference.get("locator"))
        if any(isinstance(candidate, str) and (text == candidate or candidate in text) for candidate in candidates):
            return reference
    return value
