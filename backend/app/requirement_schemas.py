from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


PackageName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
RequirementFormat = Literal[
    "markdown", "text", "json", "yaml", "openapi", "docx", "pdf", "png", "jpg", "unsupported"
]
ParseStatus = Literal["complete", "partial", "failed", "rejected"]


class RequirementFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: int = Field(gt=0)
    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    media_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    content_base64: str = ""


class RequirementPackageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PackageName = "当前任务"
    files: Annotated[list[RequirementFileInput], Field(min_length=1, max_length=20)]


class SourceReference(BaseModel):
    reference_id: str
    asset_id: int
    filename: str
    locator: str


class ParsedFragment(BaseModel):
    text: str
    source_reference: SourceReference


class VisualInferenceCandidate(BaseModel):
    """图片只产生待确认线索，不直接成为需求事实。"""

    status: Literal["pending_confirmation"] = "pending_confirmation"
    description: str
    source_reference: SourceReference


class ParseDiagnostic(BaseModel):
    asset_id: int
    filename: str
    code: str
    severity: Literal["warning", "error"] = "error"
    message: str


class RequirementMaterial(BaseModel):
    asset_id: int
    asset_revision: int
    filename: str
    media_type: str
    format: RequirementFormat
    sha256: str
    content_base64: str
    parse_status: ParseStatus
    fragments: list[ParsedFragment]
    visual_inferences: list[VisualInferenceCandidate] = Field(default_factory=list)
    diagnostics: list[ParseDiagnostic]


class RequirementPackage(BaseModel):
    id: int
    project_id: int
    name: str
    status: Literal["draft", "published"]
    materials: list[RequirementMaterial]
    diagnostics: list[ParseDiagnostic]
    created_at: datetime
    published_version_id: int | None = None


class RequirementVersion(BaseModel):
    id: int
    project_id: int
    package_id: int
    version: int
    name: str
    materials: list[RequirementMaterial]
    diagnostics: list[ParseDiagnostic]
    created_at: datetime
