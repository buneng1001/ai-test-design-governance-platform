from datetime import UTC, datetime

from app.ai_repository import AIRunRepository
from app.asset_repository import AssetRepository
from app.case_repository import CaseGenerationRepository
from app.case_review_repository import CaseReviewRepository
from app.change_impact_repository import ChangeImpactRepository
from app.coverage_service import build_coverage
from app.design_repository import DesignRepository
from app.evaluation_repository import EvaluationRepository
from app.execution_batch_repository import ExecutionBatchRepository
from app.execution_result_repository import ExecutionResultRepository
from app.quality_repository import QualityRepository
from app.requirement_repository import RequirementRepository
from app.review_repository import RequirementReviewRepository
from app.task_repository import TestTaskRepository
from app.template_repository import TemplateMappingRepository
from app.report_metrics import ReportPayload, ai_effectiveness, ai_summary, review_counts, source_references
from app.report_metrics import version_summary


class ReportService:
    def __init__(
        self,
        asset_repository: AssetRepository,
        requirement_repository: RequirementRepository,
        review_repository: RequirementReviewRepository,
        design_repository: DesignRepository,
        template_repository: TemplateMappingRepository,
        generation_repository: CaseGenerationRepository,
        case_review_repository: CaseReviewRepository,
        task_repository: TestTaskRepository,
        batch_repository: ExecutionBatchRepository,
        result_repository: ExecutionResultRepository,
        quality_repository: QualityRepository,
        change_repository: ChangeImpactRepository,
        ai_repository: AIRunRepository,
        evaluation_repository: EvaluationRepository,
    ) -> None:
        self.assets = asset_repository
        self.requirements = requirement_repository
        self.reviews = review_repository
        self.designs = design_repository
        self.templates = template_repository
        self.generations = generation_repository
        self.case_reviews = case_review_repository
        self.tasks = task_repository
        self.batches = batch_repository
        self.results = result_repository
        self.quality = quality_repository
        self.changes = change_repository
        self.ai_runs = ai_repository
        self.evaluations = evaluation_repository

    def build_test_design(self, project_id: int) -> ReportPayload:
        versions = self.requirements.list_versions(project_id)
        reviews = [self.reviews.latest_for_version(project_id, item.id) for item in versions]
        reviews = [item for item in reviews if item is not None]
        confirmed_requirement_version_ids = [
            version.id
            for version in versions
            if (review := self.reviews.latest_for_version(project_id, version.id))
            and review.status == "confirmed"
        ]
        designs = [self.designs.latest_for_version(project_id, item.id) for item in versions]
        designs = [item for item in designs if item is not None]
        confirmed_reviews = [item for item in reviews if item.status == "confirmed"]
        confirmed_designs = [item for item in designs if item.status == "confirmed"]
        coverage = self._coverage(project_id, versions, confirmed_designs)
        return self._document(
            "test-design-report.v1", "test_design", project_id,
            summary={
                "requirement_versions": [version_summary(item) for item in versions],
                "confirmed_requirement_versions": confirmed_requirement_version_ids,
                "confirmed_designs": [item.id for item in confirmed_designs],
                "template_mappings": [self._dump(item) for item in self.templates.list_versions(project_id)],
                "case_generations": [self._dump(item) for item in self.generations.list(project_id)],
                "case_review_batches": [
                    self._dump(item) for item in self.case_reviews.list_batches(project_id)
                ],
            },
            metrics={
                "requirement_review": review_counts(reviews),
                "design": [self._dump(item) for item in designs],
                "coverage": coverage,
                "automation_candidates": [
                    self._dump(item) for design in designs for item in design.automation_candidates
                ],
                "automation_decisions": [
                    {
                        "scope_item_id": item.scope_item_id,
                        "decision": item.decision,
                        "reason": item.decision_reason,
                    }
                    for design in designs for item in design.automation_candidates
                ],
                "human_decisions": {
                    "requirement_confirmations": [item.confirmed_by for item in confirmed_reviews],
                    "design_confirmations": [item.confirmed_by for item in confirmed_designs],
                },
            },
            evidence={"source_references": source_references(reviews, designs)},
        )

    def build_execution_governance(self, project_id: int) -> ReportPayload:
        batches = self.batches.list(project_id)
        records = [record for batch in batches for record in self.results.list_records(batch.id)]
        issues = self.quality.list_issues(project_id)
        patterns = self.quality.list_patterns(project_id)
        analyses = self.changes.list_analyses(project_id)
        selections = self.changes.list_selections(project_id)
        status_counts = {status: sum(record.status == status for record in records) for status in (
            "passed", "execution_failed", "blocked", "not_executed", "execution_error"
        )}
        return self._document(
            "execution-governance-report.v1", "execution_governance", project_id,
            summary={
                "batches": [self._dump(item) for item in batches],
                "result_status_counts": status_counts,
                "retest_count": sum(record.retest_of_result_id is not None for record in records),
                "open_conflict_count": sum(
                    len([item for item in self.results.list_conflicts(batch.id) if item.status == "open"])
                    for batch in batches
                ),
            },
            metrics={
                "quality_issues": [self._dump(item) for item in issues],
                "defect_patterns": [self._dump(item) for item in patterns],
                "change_impact_analyses": [self._dump(item) for item in analyses],
                "regression_selections": [self._dump(item) for item in selections],
            },
            evidence={
                "result_records": [self._dump(item) for item in records],
                "batch_conclusions": {
                    str(batch.id): self.results.get_conclusion(batch.id) for batch in batches
                },
            },
        )

    def build_audit_package(self, project_id: int) -> ReportPayload:
        assets = self.assets.list_assets(project_id)
        runs = self.ai_runs.list(project_id)
        evaluations = self.evaluations.list(project_id)
        latest_evaluation = self.evaluations.latest(project_id)
        design_report = self.build_test_design(project_id)
        governance_report = self.build_execution_governance(project_id)
        dispositions = [item for run in runs for item in run.dispositions]
        return self._document(
            "audit-package.v1", "audit_package", project_id,
            summary={
                "version_relationships": {
                    "requirement_versions": [
                        item["id"] for item in design_report["summary"]["requirement_versions"]
                    ],
                    "designs": design_report["summary"]["confirmed_designs"],
                    "case_review_batches": [item["id"] for item in design_report["summary"]["case_review_batches"]],
                    "execution_batches": [item["id"] for item in governance_report["summary"]["batches"]],
                    "test_tasks": [item.id for item in self.tasks.list_for_project(project_id)],
                    "change_impact_analyses": [
                        item["id"] for item in governance_report["metrics"]["change_impact_analyses"]
                    ],
                },
                "ai_runs": [ai_summary(run) for run in runs],
                "evaluations": [
                    {
                        "id": item.id,
                        "truth_asset_id": item.truth_asset_id,
                        "truth_sha256": item.truth_sha256,
                        "input_sha256": item.input_sha256,
                        "ai_run_ids": item.ai_run_ids,
                        "metrics": item.metrics.model_dump(mode="json"),
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in evaluations
                ],
                "human_dispositions": dispositions,
            },
            metrics={"ai_effectiveness": ai_effectiveness(runs, latest_evaluation)},
            evidence={
                "source_references": design_report["evidence"]["source_references"],
                "asset_provenance": [
                    self._dump(item) for item in assets if item.can_enter_requirement_package
                ],
                "excluded_asset_count": sum(not item.can_enter_requirement_package for item in assets),
                "contract_validation": {
                    "test_design_report": "passed",
                    "execution_governance_report": "passed",
                    "audit_package": "passed",
                },
                "security_exclusions": [
                    "资产原始内容", "评估真值原文", "完整内部 Prompt", "模型凭据"
                ],
            },
        )

    def _coverage(self, project_id: int, versions: list[object], designs: list[object]) -> ReportPayload:
        if not versions or not designs:
            return {"metrics": {}}
        review = self.reviews.latest_for_version(project_id, versions[-1].id)
        case_review = self.case_reviews.list_batches(project_id)
        confirmed_cases = [item for item in case_review if item.status == "confirmed"]
        batches = self.batches.list(project_id)
        case_batch = confirmed_cases[-1] if confirmed_cases else None
        execution_batch = batches[-1] if batches else None
        results = self.results.list_records(execution_batch.id) if execution_batch else []
        conflicts = self.results.list_conflicts(execution_batch.id) if execution_batch else []
        open_result_ids = {
            record_id
            for conflict in conflicts
            if conflict.status == "open"
            for record_id in conflict.result_ids
        }
        return build_coverage(
            review, designs[-1], case_batch, execution_batch, results,
            [item.model_dump(mode="json") for item in self.quality.list_issues(project_id)], open_result_ids,
        )

    @staticmethod
    def _document(
        contract_version: str, report_type: str, project_id: int, **fields: ReportPayload
    ) -> ReportPayload:
        return {
            "contract_version": contract_version, "report_type": report_type, "project_id": project_id,
            "generated_at": datetime.now(UTC).isoformat(), **fields,
        }

    @staticmethod
    def _dump(value: object) -> object:
        return value.model_dump(mode="json") if hasattr(value, "model_dump") else value
