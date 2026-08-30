// 用例生成、评审与发布领域请求。
import { request, downloadResponseFile, sessionHeaders } from "./api_client";
import type { CaseGeneration, CaseReviewBatch, TestTask } from "./api_types";

export const generateCases = (projectId: number, designId: number, templateMappingId: number,
  acceptTemplateLimitations = false, strictConflicts = false, modules: string[] = [],
    mode: "mock" | "real" = "mock"): Promise<CaseGeneration> => request(
  `/api/projects/${projectId}/test-designs/${designId}/case-generations`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      ...(templateMappingId > 0 ? { template_mapping_id: templateMappingId } : {}),
        accept_template_limitations: acceptTemplateLimitations,
      variants: ["normal", "boundary", "invalid"], strict_conflicts: strictConflicts, modules, mode,
    }),
  },
);
export const createCaseReviews = (projectId: number, generationId: number,
  mode: "mock" | "real" = "mock"): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-generations/${generationId}/reviews`, {
    method: "POST", headers: { ...sessionHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
  },
);
export const disposeCaseReviewSuggestion = (projectId: number, batchId: number, suggestionId: string,
  decision: "accepted" | "rejected" | "modified", modifiedFields: Record<string,
    string> = {}): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/suggestions/${suggestionId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision,
      reason: `测试工程师${decision === "accepted" ? "采纳" : decision === "rejected" ? "拒绝" : "修改并采纳"}该建议`,
        modified_fields: modifiedFields }),
  },
);
export const confirmCaseReviews = (projectId: number, batchId: number, candidateIds: string[], confirmerName: string,
  excludedCandidateIds: string[] = []): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmer_name: confirmerName,
        inclusion: Object.fromEntries(candidateIds.map((candidateId) => [candidateId,
          !excludedCandidateIds.includes(candidateId)])) }),
  },
);
export const changeCaseStatus = (projectId: number, batchId: number, stableCaseId: string,
  lifecycleStatus: CaseReviewBatch["revisions"][number]["lifecycle_status"],
    participationStatus: CaseReviewBatch["revisions"][number]["participation_status"]
  ): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/cases/${stableCaseId}/status`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lifecycle_status: lifecycleStatus, participation_status: participationStatus,
        reason: "测试工程师更新用例状态", confirmer_name: "测试工程师" }),
  },
);
export const editCase = (projectId: number, batchId: number, caseId: string, fields: Record<string,
  unknown>): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/cases/${caseId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fields),
  },
);
export const changeCaseStatuses = (projectId: number, batchId: number, stableCaseIds: string[],
  participationStatus: "included" | "not_included"): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/cases/bulk-status`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stable_case_ids: stableCaseIds, participation_status: participationStatus,
        reason: participationStatus === "included" ? "恢复纳入本次用例集" : "移除出本次用例集", confirmer_name: "测试工程师" }),
  },
);
export const exportCaseFile = async (projectId: number, batchId: number, scope: "all" | "selected" | "changed" = "all",
  stableCaseIds: string[] = []): Promise<void> => {
  const response = await fetch(`/api/projects/${projectId}/case-review-batches/${batchId}/export`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scope,
      stable_case_ids: stableCaseIds }),
  });
  await downloadResponseFile(response, "test-cases.csv");
};
export const publishTestTask = (projectId: number, batchId: number,
  input: {
    confirmer_name: string;
    execution_target: TestTask["execution_target"];
    stable_case_ids: string[];
    target_extension: Record<string, string>;
  }): Promise<TestTask> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/test-tasks`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  },
);
