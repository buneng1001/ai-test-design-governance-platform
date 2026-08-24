import json
from pathlib import Path
from typing import Any

import yaml

from app.requirement_schemas import ParsedFragment, RequirementFormat, SourceReference


SUPPORTED_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}


class RequirementParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_requirement(
    asset_id: int,
    filename: str,
    content: bytes,
    sha256: str,
) -> tuple[RequirementFormat, list[ParsedFragment]]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise RequirementParseError("unsupported_format", f"不支持的需求资料格式：{suffix or '无扩展名'}")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise RequirementParseError("unreadable_content", "需求资料不是可读取的 UTF-8 文本") from error
    if suffix in {".md", ".txt"}:
        format_name: RequirementFormat = "markdown" if suffix == ".md" else "text"
        fragments = _line_fragments(asset_id, filename, text, sha256)
        if not fragments:
            raise RequirementParseError("empty_content", "需求资料没有可提取的文本内容")
        return format_name, fragments
    try:
        data = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise RequirementParseError("malformed_content", f"结构化需求资料格式错误：{error}") from error
    if not isinstance(data, (dict, list)):
        raise RequirementParseError("malformed_content", "结构化需求资料顶层必须是对象或数组")
    is_openapi = isinstance(data, dict) and ("openapi" in data or "swagger" in data)
    format_name = "openapi" if is_openapi else ("json" if suffix == ".json" else "yaml")
    skipped_keys = {"openapi", "swagger"} if is_openapi else set()
    fragments = _structured_fragments(asset_id, filename, data, sha256, skipped_keys=skipped_keys)
    if not fragments:
        raise RequirementParseError("empty_content", "结构化需求资料没有可提取的内容")
    return format_name, fragments


def openapi_is_partial(content: bytes) -> bool:
    """OpenAPI 缺少 paths 时仍保留可读元数据，但必须明确标记为部分解析。"""
    try:
        data = yaml.safe_load(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, yaml.YAMLError):
        return False
    return isinstance(data, dict) and ("openapi" in data or "swagger" in data) and "paths" not in data


def _line_fragments(asset_id: int, filename: str, text: str, sha256: str) -> list[ParsedFragment]:
    fragments = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        normalized = line.strip()
        if not normalized:
            continue
        fragments.append(_fragment(asset_id, filename, normalized, f"lines:{line_number}-{line_number}", sha256))
    return fragments


def _structured_fragments(
    asset_id: int,
    filename: str,
    value: Any,
    sha256: str,
    pointer: str = "",
    skipped_keys: set[str] | None = None,
) -> list[ParsedFragment]:
    fragments: list[ParsedFragment] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if not pointer and key in (skipped_keys or set()):
                continue
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            fragments.extend(
                _structured_fragments(asset_id, filename, child, sha256, f"{pointer}/{escaped}")
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            fragments.extend(_structured_fragments(asset_id, filename, child, sha256, f"{pointer}/{index}"))
    else:
        fragments.append(_fragment(asset_id, filename, str(value), pointer or "/", sha256))
    return fragments


def _fragment(asset_id: int, filename: str, text: str, locator: str, sha256: str) -> ParsedFragment:
    return ParsedFragment(
        text=text,
        source_reference=SourceReference(
            reference_id=f"src-{asset_id}-{sha256[:12]}-{locator}",
            asset_id=asset_id,
            filename=filename,
            locator=locator,
        ),
    )
