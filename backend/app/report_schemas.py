from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


ReportType = Literal["test_design", "execution_governance", "audit_package"]


class ReportDocument(BaseModel):
    """独立交付物的通用外壳，正文按报告类型保存可追踪的结构化事实。"""

    model_config = ConfigDict(extra="forbid")

    contract_version: str
    report_type: ReportType
    project_id: int
    generated_at: datetime
    summary: dict[str, object]
    metrics: dict[str, object]
    evidence: dict[str, object]
