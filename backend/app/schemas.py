from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
TestObjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
SoftwareVersion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_language: Literal["zh-CN", "en-US"] = "zh-CN"


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    test_object: TestObjectName
    software_version: SoftwareVersion
    description: Annotated[str, Field(max_length=2000)] = ""
    settings: ProjectSettings = Field(default_factory=ProjectSettings)


class Project(ProjectInput):
    id: int
    created_at: datetime
    updated_at: datetime
