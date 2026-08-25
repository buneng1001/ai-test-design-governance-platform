from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


EvaluationCategory = Literal["review_finding", "key_scope", "risk", "change_impact", "other"]
EvaluationText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class EvaluationTruthItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    truth_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    category: EvaluationCategory
    key: EvaluationText
    match_terms: list[EvaluationText] = Field(default_factory=list, max_length=10)


class EvaluationRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    truth_asset_id: int = Field(gt=0)
    ai_run_ids: list[int] = Field(min_length=1, max_length=100)


class EvaluationMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    percentage: float = Field(ge=0, le=100)


class EvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    truth_hit: EvaluationMetric
    key_omissions: EvaluationMetric
    unsupported_expansions: EvaluationMetric
    distractor_hits: EvaluationMetric
    output_item_count: int = Field(ge=0)
    matched_output_item_count: int = Field(ge=0)


class EvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["ai-evaluation.v1"] = "ai-evaluation.v1"
    id: int
    project_id: int
    truth_asset_id: int
    truth_sha256: str
    input_sha256: str
    ai_run_ids: list[int]
    metrics: EvaluationMetrics
    unmatched_output_candidate_ids: list[str] = Field(default_factory=list)
    created_at: datetime
