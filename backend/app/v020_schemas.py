from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class MaterialUploadFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    media_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    content_base64: str


class MaterialUploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplemental_notes: Annotated[str, Field(max_length=4000)] = ""
    files: Annotated[list[MaterialUploadFile], Field(min_length=1, max_length=20)]


class ArchiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archived: bool


class ProjectSummary(BaseModel):
    id: int
    name: str
    test_object: str
    software_version: str
    updated_at: datetime
    archived_at: datetime | None
    current_requirement_version: int | None
    latest_analysis_status: str
    latest_case_status: str
    latest_export_at: datetime | None

