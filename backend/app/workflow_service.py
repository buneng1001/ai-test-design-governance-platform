from app.case_repository import CaseGenerationRepository
from app.case_review_repository import CaseReviewRepository
from app.design_repository import DesignRepository
from app.requirement_repository import RequirementRepository
from app.review_repository import RequirementReviewRepository
from app.workflow_contracts import STAGE_IDS
from app.workflow_schemas import ProjectWorkflowView, WorkflowAction, WorkflowAssetIds, WorkflowTab


TAB_STAGE_IDS = {
    "upload": ["S00"],
    "preview": ["S01", "S02"],
    "suggestions": ["S03", "S04", "S05", "S06"],
    "review": ["S07", "S08"],
    "cases": [],
}
if not {stage for stages in TAB_STAGE_IDS.values() for stage in stages}.issubset(STAGE_IDS):
    raise RuntimeError("五页签引用了未在工作流契约中定义的阶段")


def build_project_workflow_view(
    project_id: int,
    requirements: RequirementRepository,
    reviews: RequirementReviewRepository,
    designs: DesignRepository,
    generations: CaseGenerationRepository,
    case_reviews: CaseReviewRepository,
) -> ProjectWorkflowView:
    """由已有领域资产推导主流程，刷新后无需依赖浏览器内存恢复。"""
    versions = requirements.list_versions(project_id)
    version = versions[-1] if versions else None
    analysis = reviews.latest_for_version(project_id, version.id) if version else None
    selected = bool(analysis and analysis.selected_requirement_ids)
    pending_suggestions = [
        item for item in analysis.suggestions
        if item.disposition in {"pending_confirmation", "awaiting_external_confirmation"}
    ] if analysis else []
    blocked_requirement_ids = sorted({
        requirement_id for suggestion in pending_suggestions for requirement_id in suggestion.related_requirement_ids
    })
    suggestions_generated = bool(analysis and analysis.suggestions)
    suggestions_completed = bool(analysis and analysis.suggestions and not pending_suggestions)
    test_point_review = analysis.test_point_review if analysis else None
    review_scope_selected = bool(test_point_review and (
        test_point_review.selected_test_item_ids or test_point_review.selected_test_point_ids
    ))
    review_completed = bool(test_point_review and test_point_review.status == "confirmed" and review_scope_selected)
    design = designs.latest_for_version(project_id, version.id) if version else None
    generation = next((item for item in generations.list(project_id) if design and item.design_id == design.id), None)
    batch = case_reviews.latest_for_generation(project_id, generation.id) if generation else None
    invalidated = [item.id for item in designs.list_for_project(project_id) if version and item.requirement_version_id != version.id
                   and item.status == "draft"]

    tabs = [
        WorkflowTab(id="upload", label="上传文档", stage_ids=TAB_STAGE_IDS["upload"], status="completed" if version else "current"),
        WorkflowTab(
            id="preview", label="结构预览", stage_ids=TAB_STAGE_IDS["preview"],
            status="completed" if analysis and analysis.status == "confirmed" else "current" if version else "locked",
            blocked_reason=None if version else "请先上传并发布至少一份可解析的需求资料。",
        ),
        WorkflowTab(
            id="suggestions", label="新增建议", stage_ids=TAB_STAGE_IDS["suggestions"],
            status="completed" if suggestions_completed else "needs_attention" if pending_suggestions
            else "current" if analysis and analysis.status == "confirmed" and selected else "locked",
            blocked_reason="仍有待处置新增建议；它们只影响关联需求或模块。" if pending_suggestions
            else None if analysis and analysis.status == "confirmed" and selected
            else "请先确认结构预览中的需求，并至少选择一项进入分析范围。",
            blocked_requirement_ids=blocked_requirement_ids,
        ),
        WorkflowTab(
            id="review", label="审核", stage_ids=TAB_STAGE_IDS["review"],
            status="completed" if review_completed else "current" if suggestions_generated else "locked",
            blocked_reason="仍有待处置建议；审核时仅应排除其关联需求或模块。" if pending_suggestions
            else "请在审核页选择至少一个测试项或测试点，确认后才能生成用例。"
            if test_point_review and test_point_review.status == "confirmed" and not review_scope_selected
            else None if suggestions_generated else "请先生成 S03–S06 新增建议，再审核测试点与覆盖。",
            blocked_requirement_ids=blocked_requirement_ids,
        ),
        WorkflowTab(
            id="cases", label="测试用例", stage_ids=TAB_STAGE_IDS["cases"],
            status="current" if review_completed else "locked",
            blocked_reason=None if review_completed else "请先完成 S07–S08 审核、覆盖检查和生成范围确认。",
        ),
    ]
    if invalidated:
        tabs[2] = tabs[2].model_copy(update={
            "status": "needs_reconfirmation",
            "blocked_reason": "上游需求版本已更新；受影响的下游草稿需要重新确认，不能继续沿用。",
        })

    # 待处置建议必须把用户带回建议页，否则刷新会直接跳到审核页，导致普通主流程看不到处置入口。
    current = next((item for item in tabs if item.status == "needs_attention"), None)
    current = current or next((item for item in tabs if item.status == "current"), tabs[-1])
    if invalidated:
        current = tabs[2]
    action = WorkflowAction(label=_action_label(current.id, current.status), target_tab=current.id)
    blockers = [item.blocked_reason for item in tabs if item.blocked_reason]
    return ProjectWorkflowView(
        project_id=project_id,
        current_step=current.id,
        progress=sum(item.status == "completed" for item in tabs),
        tabs=tabs,
        blockers=blockers,
        next_action=action,
        asset_ids=WorkflowAssetIds(
            requirement_version_id=version.id if version else None,
            requirement_analysis_id=analysis.id if analysis else None,
            test_point_review_id=test_point_review.review_id if test_point_review else None,
            test_design_id=design.id if design else None,
            case_generation_id=generation.id if generation else None,
            case_review_batch_id=batch.id if batch else None,
        ),
        invalidated_draft_ids=invalidated,
    )


def _action_label(tab_id: str, status: str) -> str:
    if status == "needs_reconfirmation":
        return "重新确认受影响的下游草稿"
    return {
        "upload": "上传并发布需求资料",
        "preview": "查看结构预览并确认需求",
        "suggestions": "处理新增建议",
        "review": "审核测试点并选择生成范围",
        "cases": "生成并管理测试用例",
    }[tab_id]
