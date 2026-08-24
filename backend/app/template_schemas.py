from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


TemplateFormat = Literal["xlsx", "csv"]
SheetRole = Literal["case", "instruction", "dictionary", "statistics", "unknown"]
TemplateStatus = Literal["draft", "confirmed"]


class TemplateUploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    media_type: str = "application/octet-stream"
    content_base64: Annotated[str, StringConstraints(min_length=1)]


class TemplateColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    name: str
    sample_values: list[str] = Field(default_factory=list)


class TemplateDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["warning", "error"]
    message: str
    sheet_name: str | None = None


class TemplateSheet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    index: int = Field(ge=0)
    role_suggestion: SheetRole
    role: SheetRole = "unknown"
    title_row_candidates: list[int] = Field(default_factory=list)
    title_row: int | None = Field(default=None, ge=1)
    columns: list[TemplateColumn] = Field(default_factory=list)
    participates: bool = False
    field_mapping: dict[str, str] = Field(default_factory=dict)
    diagnostics: list[TemplateDiagnostic] = Field(default_factory=list)


class TemplateMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet_name: str
    role: SheetRole
    participates: bool
    title_row: int | None = Field(default=None, ge=1)
    field_mapping: dict[str, str] = Field(default_factory=dict)


class TemplateConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    mappings: list[TemplateMapping] = Field(min_length=1)


class TemplateMappingVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    version: int
    filename: str
    format: TemplateFormat
    status: TemplateStatus = "draft"
    sheets: list[TemplateSheet] = Field(min_length=1)
    diagnostics: list[TemplateDiagnostic] = Field(default_factory=list)
    retained_sheet_names: list[str] = Field(default_factory=list)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None


class TemplateValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    diagnostics: list[TemplateDiagnostic] = Field(default_factory=list)
