import base64
from datetime import UTC, datetime

from app.asset_repository import AssetRepository
from app.requirement_parser import RequirementParseError, openapi_is_partial, parse_requirement
from app.requirement_schemas import (
    ParseDiagnostic,
    RequirementFileInput,
    RequirementMaterial,
    RequirementPackage,
    RequirementPackageInput,
)


MAX_REQUIREMENT_FILE_SIZE = 2 * 1024 * 1024


def build_requirement_package(
    project_id: int,
    package_input: RequirementPackageInput,
    asset_repository: AssetRepository,
) -> RequirementPackage:
    materials = [build_material(project_id, item, asset_repository) for item in package_input.files]
    return RequirementPackage(
        id=0,
        project_id=project_id,
        name=package_input.name,
        status="draft",
        materials=materials,
        diagnostics=[diagnostic for material in materials for diagnostic in material.diagnostics],
        created_at=datetime.now(UTC),
    )


def build_material(
    project_id: int,
    file_input: RequirementFileInput,
    asset_repository: AssetRepository,
) -> RequirementMaterial:
    asset = asset_repository.get(project_id, file_input.asset_id)
    if asset is None:
        return _failed_material(file_input, "asset_not_found", "资产来源记录不存在", "rejected")
    if not asset.can_enter_requirement_package:
        return _failed_material(file_input, "asset_not_allowed", asset.reason, "rejected", asset.revision, asset.sha256)
    try:
        content = base64.b64decode(file_input.content_base64, validate=True)
    except ValueError:
        return _failed_material(file_input, "unreadable_content", "文件内容不是有效的 Base64", "failed")
    actual_sha256 = asset_repository.hash_content(file_input.content_base64)
    if actual_sha256 != asset.sha256:
        return _failed_material(
            file_input,
            "asset_hash_mismatch",
            "文件内容与最新资产来源记录的 SHA-256 不一致",
            "rejected",
            asset.revision,
            asset.sha256,
        )
    if len(content) > MAX_REQUIREMENT_FILE_SIZE:
        return _failed_material(
            file_input,
            "file_too_large",
            "单份需求资料不能超过 2 MiB",
            "rejected",
            asset.revision,
            asset.sha256,
        )
    try:
        format_name, fragments = parse_requirement(asset.id, file_input.filename, content, asset.sha256)
    except RequirementParseError as error:
        return _failed_material(
            file_input,
            error.code,
            str(error),
            "failed",
            asset.revision,
            asset.sha256,
        )
    diagnostics = []
    parse_status = "complete"
    if format_name == "openapi" and openapi_is_partial(content):
        parse_status = "partial"
        diagnostics = [ParseDiagnostic(
            asset_id=asset.id,
            filename=file_input.filename,
            code="partial_openapi",
            severity="warning",
            message="OpenAPI 缺少 paths，已保留可读取的元数据并标记为部分解析",
        )]
    return RequirementMaterial(
        asset_id=asset.id,
        asset_revision=asset.revision,
        filename=file_input.filename,
        media_type=file_input.media_type,
        format=format_name,
        sha256=asset.sha256,
        content_base64=file_input.content_base64,
        parse_status=parse_status,
        fragments=fragments,
        diagnostics=diagnostics,
    )


def _failed_material(
    file_input: RequirementFileInput,
    code: str,
    message: str,
    status: str,
    asset_revision: int = 0,
    sha256: str = "",
) -> RequirementMaterial:
    diagnostic = ParseDiagnostic(
        asset_id=file_input.asset_id,
        filename=file_input.filename,
        code=code,
        message=message,
    )
    return RequirementMaterial(
        asset_id=file_input.asset_id,
        asset_revision=asset_revision,
        filename=file_input.filename,
        media_type=file_input.media_type,
        format="unsupported",
        sha256=sha256,
        content_base64=file_input.content_base64,
        parse_status=status,
        fragments=[],
        diagnostics=[diagnostic],
    )
