// 需求导入与评审领域请求。
import { request, sessionHeaders } from "./api_client";
import type { RequirementFileInput, RequirementAnalysis, RequirementPackage, RequirementVersion } from "./api_types";

export const createRequirementPackage = (projectId: number, name: string,
  files: RequirementFileInput[]): Promise<RequirementPackage> =>
  request(`/api/projects/${projectId}/requirement-packages`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, files }),
  });
export const publishRequirementPackage = (projectId: number, packageId: number): Promise<RequirementVersion> =>
  request(`/api/projects/${projectId}/requirement-packages/${packageId}/publish`, { method: "POST" });
export const listRequirementVersions = (projectId: number): Promise<RequirementVersion[]> =>
  request(`/api/projects/${projectId}/requirement-versions`);
export const createRequirementReview = (projectId: number, versionId: number,
  mode: "mock" | "real" = "mock", forceNew = false): Promise<RequirementAnalysis> =>
  request(`/api/projects/${projectId}/requirement-versions/${versionId}/requirement-review`, {
    method: "POST", headers: { ...sessionHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ mode, force_new: forceNew }),
  });
export const updateAtomicRequirement = (projectId: number, analysisId: number, candidateId: string,
  input: { decision: "accepted" | "rejected"; statement?: string }): Promise<RequirementAnalysis> =>
  request(`/api/projects/${projectId}/requirement-reviews/${analysisId}/atomic-requirements/${candidateId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
export const bulkConfirmAtomicRequirements = (projectId: number, analysisId: number,
  candidateIds: string[]): Promise<RequirementAnalysis> => request(
  `/api/projects/${projectId}/requirement-reviews/${analysisId}/atomic-requirements/bulk-confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_ids: candidateIds }),
  });
export const updateFinding = (projectId: number, analysisId: number, findingId: string,
  status: string, summary?: string, reason?: string): Promise<RequirementAnalysis> =>
  request(`/api/projects/${projectId}/requirement-reviews/${analysisId}/findings/${findingId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, ...(summary ? { summary } : {}), ...(reason ? { reason } : {}) }),
  });
export const updateVisualInference = (projectId: number, analysisId: number, inferenceId: string,
  decision: "accepted" | "rejected"): Promise<RequirementAnalysis> =>
  request(`/api/projects/${projectId}/requirement-reviews/${analysisId}/visual-inferences/${inferenceId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }),
  });
export const confirmRequirementReview = (projectId: number, analysisId: number,
  confirmerName: string): Promise<RequirementAnalysis> =>
  request(`/api/projects/${projectId}/requirement-reviews/${analysisId}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmer_name: confirmerName }),
  });
export const updateRequirementSelection = (projectId: number, analysisId: number,
  selectedRequirementIds: string[]): Promise<RequirementAnalysis> =>
  request(`/api/projects/${projectId}/requirement-reviews/${analysisId}/selection`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_requirement_ids: selectedRequirementIds }),
  });
export const decideRequirementConflict = (projectId: number, analysisId: number, conflictId: string,
  decision: RequirementAnalysis["conflicts"][number]["decision"],
    confirmerName: string): Promise<RequirementAnalysis> =>
  request(`/api/projects/${projectId}/requirement-reviews/${analysisId}/conflicts/${conflictId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision,
      confirmer_name: confirmerName }),
  });
