from dataclasses import dataclass

from app.ai_repository import AIRunRepository
from app.ai_service import MockModelService, OpenAICompatibleModelService
from app.case_repository import CaseGenerationRepository
from app.case_review_repository import CaseReviewRepository
from app.repository import ProjectRepository
from app.requirement_repository import RequirementRepository
from app.template_repository import TemplateMappingRepository


@dataclass(frozen=True)
class CaseReviewRouteDependencies:
    """评审相关路由共享的仓储和模型服务依赖。"""

    projects: ProjectRepository
    generations: CaseGenerationRepository
    reviews: CaseReviewRepository
    ai_runs: AIRunRepository
    requirements: RequirementRepository
    templates: TemplateMappingRepository
    mock_service: MockModelService
    real_model_service: OpenAICompatibleModelService
