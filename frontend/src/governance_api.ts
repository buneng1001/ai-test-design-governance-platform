// 覆盖率、变更影响、回归选择和审计报告领域请求。
import { request } from "./api_client";
import type { ChangeImpactAnalysis, CoverageSummary, RegressionSelection, ReportDocument } from "./api_types";

export const getCoverage = (projectId: number, requirementVersionId: number, designId: number,
  caseReviewBatchId: number, executionBatchId?: number): Promise<CoverageSummary> => {
  const params = new URLSearchParams({ requirement_version_id: String(requirementVersionId),
    design_id: String(designId), case_review_batch_id: String(caseReviewBatchId) });
  if (executionBatchId) params.set("execution_batch_id", String(executionBatchId));
  return request(`/api/projects/${projectId}/coverage?${params.toString()}`);
};
export const createChangeImpact = (projectId: number, baseVersionId: number,
  targetVersionId: number): Promise<ChangeImpactAnalysis> => request(
  `/api/projects/${projectId}/change-impact-analyses`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ base_version_id: baseVersionId,
      target_version_id: targetVersionId }) },
);
export const confirmChangeImpact = (projectId: number, analysisId: number,
  changes: ChangeImpactAnalysis["changes"]): Promise<ChangeImpactAnalysis> => request(
  `/api/projects/${projectId}/change-impact-analyses/${analysisId}/confirm`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmer_name: "测试工程师",
      decisions: Object.fromEntries(changes.map((change) => [change.id, "confirmed"])) }) },
);
export const createRegressionSelection = (projectId: number, analysisId: number): Promise<RegressionSelection> =>
  request(`/api/projects/${projectId}/change-impact-analyses/${analysisId}/regression-selection`, { method: "POST" });
export const confirmRegressionSelection = (projectId: number,
  selection: RegressionSelection): Promise<RegressionSelection> => request(
  `/api/projects/${projectId}/regression-selections/${selection.id}/confirm`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmer_name: "测试工程师",
      decisions: Object.fromEntries(selection.candidates.map((candidate) => [candidate.stable_case_id, true])) }) },
);
export const getAuditPackage = (projectId: number): Promise<ReportDocument> => request(
  `/api/projects/${projectId}/reports/audit-package`,
);
