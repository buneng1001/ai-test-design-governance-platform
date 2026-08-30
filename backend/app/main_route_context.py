from dataclasses import dataclass

from app.ai_repository import AIRunRepository
from app.ai_service import MockModelService, OpenAICompatibleModelService, UnavailableModelService
from app.asset_repository import AssetRepository
from app.case_repository import CaseGenerationRepository
from app.case_review_repository import CaseReviewRepository
from app.change_impact_repository import ChangeImpactRepository
from app.design_repository import DesignRepository
from app.evaluation_repository import EvaluationRepository
from app.execution_batch_repository import ExecutionBatchRepository
from app.execution_result_repository import ExecutionResultRepository
from app.quality_repository import QualityRepository
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.review_repository import RequirementReviewRepository
from app.task_repository import TestTaskRepository
from app.template_repository import TemplateMappingRepository


@dataclass(frozen=True)
class AppRouteContext:
    """集中保存路由注册所需的仓储和服务，保持原有初始化顺序。"""

    repository: ProjectRepository
    asset_repository: AssetRepository
    requirement_repository: RequirementRepository
    review_repository: RequirementReviewRepository
    design_repository: DesignRepository
    ai_run_repository: AIRunRepository
    template_repository: TemplateMappingRepository
    case_generation_repository: CaseGenerationRepository
    case_review_repository: CaseReviewRepository
    task_repository: TestTaskRepository
    execution_batch_repository: ExecutionBatchRepository
    execution_result_repository: ExecutionResultRepository
    quality_repository: QualityRepository
    change_impact_repository: ChangeImpactRepository
    evaluation_repository: EvaluationRepository
    report_service: object
    model_service: MockModelService
    real_model_service: OpenAICompatibleModelService
    unavailable_model_service: UnavailableModelService
