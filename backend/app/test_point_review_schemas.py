from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.requirement_schemas import SourceReference


TestPointDirection = Literal["normal", "exception", "boundary", "risk", "permission"]
TestPointReviewStatus = Literal["draft", "confirmed"]


class ReviewTestItem(BaseModel):
    """Step 07 中可审核的测试项，只关联已确认的稳定需求。"""

    model_config = ConfigDict(extra="forbid")

    test_item_id: str
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    module: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    stable_requirement_ids: list[str] = Field(min_length=1, max_length=20)
    source_references: list[SourceReference] = Field(min_length=1, max_length=20)


class ReviewTestPoint(BaseModel):
    """只表达测试意图；详细步骤和预期结果由后续用例生成阶段负责。"""

    model_config = ConfigDict(extra="forbid")

    skill_test_point_id: Annotated[str, StringConstraints(pattern=r"^S07-TP-[A-Za-z0-9_-]+$")]
    platform_test_point_id: str
    test_item_id: str
    stable_requirement_ids: list[str] = Field(min_length=1, max_length=20)
    rule_ids: list[str] = Field(default_factory=list, max_length=20)
    source_references: list[SourceReference] = Field(min_length=1, max_length=20)
    direction: TestPointDirection
    objective: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def reject_case_details(self) -> "ReviewTestPoint":
        if any(marker in self.objective for marker in ("步骤", "预期结果", "1.", "①")):
            raise ValueError("测试点只描述测什么，不能包含详细步骤或预期结果")
        return self


class TestPointCoverageCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    total_confirmed_requirement_count: int = Field(ge=0)
    covered_requirement_count: int = Field(ge=0)
    uncovered_requirement_ids: list[str] = Field(default_factory=list)
    isolated_test_point_ids: list[str] = Field(default_factory=list)
    missing_test_item_ids: list[str] = Field(default_factory=list)
    direction_gaps: dict[str, list[TestPointDirection]] = Field(default_factory=dict)


class TestPointReview(BaseModel):
    """可恢复的 Step 07～08 审核与稳定交接快照。"""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    status: TestPointReviewStatus = "draft"
    modules: list[str] = Field(default_factory=list)
    test_items: list[ReviewTestItem] = Field(default_factory=list)
    test_points: list[ReviewTestPoint] = Field(default_factory=list)
    coverage_check: TestPointCoverageCheck
    selected_test_item_ids: list[str] = Field(default_factory=list)
    selected_test_point_ids: list[str] = Field(default_factory=list)
    handoff_version: str | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_hierarchy_and_stable_mapping(self) -> "TestPointReview":
        item_ids = {item.test_item_id for item in self.test_items}
        if len(item_ids) != len(self.test_items):
            raise ValueError("测试项 ID 必须唯一")
        skill_ids = {point.skill_test_point_id for point in self.test_points}
        platform_ids = {point.platform_test_point_id for point in self.test_points}
        if len(skill_ids) != len(self.test_points) or len(platform_ids) != len(self.test_points):
            raise ValueError("Skill 测试点编号与平台测试点 ID 必须一对一映射")
        items_by_id = {item.test_item_id: item for item in self.test_items}
        for point in self.test_points:
            item = items_by_id.get(point.test_item_id)
            if item is None or not set(point.stable_requirement_ids).issubset(item.stable_requirement_ids):
                raise ValueError("测试点必须关联有效测试项及其稳定需求")
        return self


class TestPointScopeSelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_item_ids: list[str] = Field(default_factory=list, max_length=200)
    test_point_ids: list[str] = Field(default_factory=list, max_length=1000)


class TestPointReviewConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
