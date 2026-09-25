from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


WorkflowTabId = Literal["upload", "preview", "suggestions", "review", "cases"]
WorkflowTabStatus = Literal["locked", "current", "completed", "needs_reconfirmation"]


class WorkflowAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    target_tab: WorkflowTabId


class WorkflowTab(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: WorkflowTabId
    label: str
    stage_ids: list[str]
    status: WorkflowTabStatus
    blocked_reason: str | None = None


class WorkflowAssetIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_version_id: int | None = None
    requirement_analysis_id: int | None = None
    test_design_id: int | None = None
    case_generation_id: int | None = None
    case_review_batch_id: int | None = None


class ProjectWorkflowView(BaseModel):
    """主流程只读聚合视图；阶段命令继续由各领域 API 负责。"""

    model_config = ConfigDict(extra="forbid")

    project_id: int
    current_step: WorkflowTabId
    progress: int = Field(ge=0, le=5)
    tabs: list[WorkflowTab] = Field(min_length=5, max_length=5)
    blockers: list[str] = Field(default_factory=list)
    next_action: WorkflowAction
    asset_ids: WorkflowAssetIds
    invalidated_draft_ids: list[int] = Field(default_factory=list)
