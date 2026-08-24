import base64
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ProvenanceKind = Literal["original_synthetic", "public_authorized", "prohibited"]
AssetType = Literal[
    "requirement_material",
    "case_template",
    "mock_output",
    "evaluation_truth",
    "result_input",
    "other",
]
UsagePermission = Literal["project_owned", "public_license", "prohibited", "unknown"]
ModelPermission = Literal["allowed", "denied", "unknown"]
Boundary = Literal["original_synthetic", "public_authorized", "prohibited", "unknown"]


class AssetProvenanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyText
    asset_type: AssetType
    provenance_kind: ProvenanceKind
    source: Annotated[str, Field(max_length=2000)]
    usage_permission: UsagePermission
    model_permission: ModelPermission
    requirement_version: NonEmptyText
    purpose: NonEmptyText
    content_base64: str
    change_reason: NonEmptyText

    @field_validator("source")
    @classmethod
    def strip_source(cls, value: str) -> str:
        return value.strip()

    @field_validator("content_base64")
    @classmethod
    def validate_content(cls, value: str) -> str:
        try:
            content = base64.b64decode(value, validate=True)
        except ValueError as error:
            raise ValueError("资产内容必须是有效的 Base64") from error
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("资产内容不能超过 10 MiB")
        return value


class AssetProvenanceRecord(BaseModel):
    id: int
    project_id: int
    revision: int
    name: str
    asset_type: AssetType
    provenance_kind: ProvenanceKind
    source: str
    usage_permission: UsagePermission
    model_permission: ModelPermission
    requirement_version: str
    purpose: str
    sha256: str
    change_reason: str
    created_at: datetime
    boundary: Boundary
    can_enter_requirement_package: bool
    can_enter_model_context: bool
    reason: str


class AssetContentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_base64: str

    _validate_content = field_validator("content_base64")(AssetProvenanceInput.validate_content.__func__)


class HashVerification(BaseModel):
    matches: bool
    expected_sha256: str
    actual_sha256: str
