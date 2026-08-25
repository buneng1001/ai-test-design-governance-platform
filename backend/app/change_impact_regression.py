from app.change_impact_data import batches_for_project, case_reviews_for_project, designs_for_project
from app.change_impact_schemas import ChangeImpactAnalysis, RegressionCandidate


def build_regression_candidates(
    project_id: int, analysis: ChangeImpactAnalysis, designs, case_reviews, batches, results, quality, tasks
) -> tuple[list[RegressionCandidate], list[RegressionCandidate]]:
    cases = {
        revision.stable_case_id: revision
        for batch in case_reviews_for_project(case_reviews, project_id)
        for revision in batch.revisions
        if revision.stable_case_id and revision.lifecycle_status == "effective"
    }
    changed_cases = {item.identifier for item in analysis.impacts if item.kind == "case"}
    changed_scopes = {
        revision.candidate.scope_item_id for case_id, revision in cases.items() if case_id in changed_cases
    }
    issues = quality.list_issues(project_id)
    issue_ids_by_case = {
        case_id: {issue.id for issue in issues if issue.stable_case_id == case_id} for case_id in cases
    }
    confirmed_pattern_issue_ids = {
        issue_id for pattern in quality.list_patterns(project_id) if pattern.status == "confirmed"
        for issue_id in pattern.quality_issue_ids
    }
    project_batches = batches_for_project(batches, project_id)
    project_records = {batch.id: results.list_records(batch.id) for batch in project_batches}
    conflict_result_ids = {
        result_id for batch in project_batches for conflict in results.list_conflicts(batch.id)
        if conflict.status == "open" for result_id in conflict.result_ids
    }
    candidates: dict[str, RegressionCandidate] = {}
    for case_id, revision in cases.items():
        reasons = []
        if case_id in changed_cases:
            reasons.append("requirement_change")
        if any(r.risk_level == "high" and r.scope_item_id == revision.candidate.scope_item_id
               for design in designs_for_project(designs, project_id) for r in design.risks):
            reasons.append("high_risk")
        if any(record.stable_case_id == case_id and record.status in {"execution_failed", "execution_error"}
               for records in project_records.values() for record in records):
            reasons.append("historical_failure")
        if any(record.id in conflict_result_ids for records in project_records.values() for record in records
               if record.stable_case_id == case_id):
            reasons.append("result_conflict")
        if issue_ids_by_case[case_id] & confirmed_pattern_issue_ids:
            reasons.append("defect_pattern")
        if revision.candidate.scope_item_id in changed_scopes and case_id not in changed_cases:
            reasons.append("adjacent_state")
        if not any(record.stable_case_id == case_id for records in project_records.values() for record in records):
            reasons.append("long_not_executed")
        if any(issue.stable_case_id == case_id and issue.status != "resolved" for issue in issues):
            reasons.append("open_quality_issue")
        if reasons:
            candidates[case_id] = RegressionCandidate(
                stable_case_id=case_id, title=revision.candidate.title, reasons=reasons
            )
    ai = [RegressionCandidate(
        stable_case_id=case_id, title=revision.candidate.title, deterministic=False,
        reasons=["ai_supplement"], ai_supplement_reason="Mock AI 建议复核当前有效用例的相邻状态",
    ) for case_id, revision in cases.items() if case_id not in candidates]
    return list(candidates.values()), ai
