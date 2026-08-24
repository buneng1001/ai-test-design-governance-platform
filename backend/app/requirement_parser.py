import json
import io
import re
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import yaml

from app.requirement_schemas import (
    ParseDiagnostic,
    ParsedFragment,
    RequirementFormat,
    SourceReference,
    VisualInferenceCandidate,
)


SUPPORTED_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".docx", ".pdf", ".png", ".jpg", ".jpeg"}


@dataclass(frozen=True)
class ParsedRequirement:
    format: RequirementFormat
    fragments: list[ParsedFragment]
    visual_inferences: list[VisualInferenceCandidate]
    diagnostics: list[ParseDiagnostic]
    parse_status: str = "complete"


class RequirementParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_requirement(
    asset_id: int,
    filename: str,
    content: bytes,
    sha256: str,
) -> ParsedRequirement:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise RequirementParseError("unsupported_format", f"不支持的需求资料格式：{suffix or '无扩展名'}")
    if suffix == ".docx":
        return _parse_docx(asset_id, filename, content, sha256)
    if suffix == ".pdf":
        return _parse_pdf(asset_id, filename, content, sha256)
    if suffix in {".png", ".jpg", ".jpeg"}:
        return _parse_image(asset_id, filename, content, sha256, suffix)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise RequirementParseError("unreadable_content", "需求资料不是可读取的 UTF-8 文本") from error
    if suffix in {".md", ".txt"}:
        format_name: RequirementFormat = "markdown" if suffix == ".md" else "text"
        fragments = _line_fragments(asset_id, filename, text, sha256)
        if not fragments:
            raise RequirementParseError("empty_content", "需求资料没有可提取的文本内容")
        return ParsedRequirement(format_name, fragments, [], [])
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
    return ParsedRequirement(format_name, fragments, [], [])


def _parse_docx(asset_id: int, filename: str, content: bytes, sha256: str) -> ParsedRequirement:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            document = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as error:
        raise RequirementParseError("malformed_content", "DOCX 不是可读取的有效文档") from error
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as error:
        raise RequirementParseError("malformed_content", "DOCX 正文 XML 损坏") from error
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    fragments: list[ParsedFragment] = []
    for paragraph_number, paragraph in enumerate(root.findall(".//w:body/w:p", namespace), start=1):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if text:
            fragments.append(_fragment(asset_id, filename, text, f"paragraph:{paragraph_number}", sha256))
    for table_number, table in enumerate(root.findall(".//w:body/w:tbl", namespace), start=1):
        for row_number, row in enumerate(table.findall("./w:tr", namespace), start=1):
            for cell_number, cell in enumerate(row.findall("./w:tc", namespace), start=1):
                paragraphs = cell.findall("./w:p", namespace)
                text = " ".join(
                    "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
                    for paragraph in paragraphs
                ).strip()
                if text:
                    locator = f"table:{table_number}:row:{row_number}:cell:{cell_number}"
                    fragments.append(_fragment(asset_id, filename, text, locator, sha256))
    if not fragments:
        raise RequirementParseError("empty_content", "DOCX 没有可提取的正文或表格内容")
    return ParsedRequirement("docx", fragments, [], [])


def _parse_pdf(asset_id: int, filename: str, content: bytes, sha256: str) -> ParsedRequirement:
    if not content.startswith(b"%PDF-"):
        raise RequirementParseError("malformed_content", "PDF 文件头无效或文件已损坏")
    if b"/Encrypt" in content:
        raise RequirementParseError("encrypted_pdf", "加密 PDF 不支持导入")
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", content, flags=re.DOTALL)
    fragments: list[ParsedFragment] = []
    diagnostics: list[ParseDiagnostic] = []
    for stream_number, stream in enumerate(streams, start=1):
        decoded = stream
        try:
            decoded = zlib.decompress(stream)
        except zlib.error:
            if b"BT" in stream and b"ET" in stream:
                diagnostics.append(ParseDiagnostic(
                    asset_id=asset_id,
                    filename=filename,
                    code="partial_pdf_text",
                    severity="warning",
                    message="PDF 存在无法解压的文本流，已保留可读取的部分内容",
                ))
        for text_number, text in enumerate(_pdf_text_strings(decoded), start=1):
            normalized = " ".join(text.split())
            if normalized:
                fragments.append(_fragment(
                    asset_id, filename, normalized, f"page-stream:{stream_number}:text:{text_number}", sha256,
                ))
    if not fragments:
        raise RequirementParseError("no_extractable_text", "PDF 没有可提取文本；扫描版 PDF 需要人工转录或 OCR")
    if diagnostics:
        return ParsedRequirement("pdf", fragments, [], diagnostics, "partial")
    return ParsedRequirement("pdf", fragments, [], [])


def _pdf_text_strings(stream: bytes) -> list[str]:
    values: list[str] = []
    pattern = rb"(?:\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]+>)\s*(?:Tj|'|\")"
    for match in re.finditer(pattern, stream):
        token_match = re.match(rb"\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]+>", match.group(0))
        if token_match is None:
            continue
        token = token_match.group(0)
        if token.startswith(b"("):
            raw = re.sub(rb"\\([()\\])", rb"\1", token[1:-1])
            values.append(raw.decode("latin-1", errors="replace"))
        else:
            try:
                values.append(bytes.fromhex(token[1:-1].decode()).decode("latin-1", errors="replace"))
            except ValueError:
                continue
    for array in re.finditer(rb"\[(.*?)\]\s*TJ", stream, flags=re.DOTALL):
        values.extend(_pdf_text_strings(array.group(1) + b" Tj"))
    return values


def _parse_image(
    asset_id: int,
    filename: str,
    content: bytes,
    sha256: str,
    suffix: str,
) -> ParsedRequirement:
    image_format = "png" if suffix == ".png" else "jpg"
    dimensions = _image_dimensions(content, image_format)
    if dimensions is None:
        raise RequirementParseError("malformed_content", f"{image_format.upper()} 图片文件损坏或格式不受支持")
    width, height = dimensions
    candidate = VisualInferenceCandidate(
        description=f"图片原始资产（{width}×{height}）可能包含界面线索，需人工确认后才能作为需求事实",
        source_reference=_source_reference(asset_id, filename, "image:original", sha256),
    )
    return ParsedRequirement(image_format, [], [candidate], [])


def _image_dimensions(content: bytes, image_format: str) -> tuple[int, int] | None:
    if image_format == "png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(content) >= 24 and content[12:16] == b"IHDR":
            return struct.unpack(">II", content[16:24])
        return None
    if image_format == "jpg" and content.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(content):
            if content[index] != 0xFF:
                index += 1
                continue
            marker = content[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(content):
                return None
            length = struct.unpack(">H", content[index:index + 2])[0]
            if marker in range(0xC0, 0xC4) and index + 7 < len(content):
                height, width = struct.unpack(">HH", content[index + 3:index + 7])
                return width, height
            index += length
    return None


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
    value: object,
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
        source_reference=_source_reference(asset_id, filename, locator, sha256),
    )


def _source_reference(asset_id: int, filename: str, locator: str, sha256: str) -> SourceReference:
    return SourceReference(
        reference_id=f"src-{asset_id}-{sha256[:12]}-{locator}",
        asset_id=asset_id,
        filename=filename,
        locator=locator,
    )
