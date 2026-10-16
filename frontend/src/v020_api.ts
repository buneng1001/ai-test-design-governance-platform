import { downloadResponseFile, request, sessionHeaders } from "./api_client";
import type { TemplateMappingVersion } from "./api_types";
import type { RequirementVersion } from "./api_types";
import type {
  AnalysisRow, CaseTemplateState, GeneratedCase, ProjectSummary, ReviewSuggestion, RunEvidence,
  MaterialUnderstanding, RunMode, RunPage, RunPreflight, Suggestion, WorkspaceState,
} from "./v020_types";

export const listProjectSummaries = (archived = false): Promise<ProjectSummary[]> =>
  request(`/api/v0.2/projects?archived=${archived}`);
export const setProjectArchived = (projectId: number, archived: boolean) =>
  request(`/api/v0.2/projects/${projectId}/archive`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ archived }),
  });
export const getV020Workspace = (projectId: number): Promise<WorkspaceState> =>
  request(`/api/v0.2/projects/${projectId}/workspace`);
export const uploadAndParseMaterials = (projectId: number, supplementalNotes: string,
  files: Array<{ filename: string; media_type: string; content_base64: string }>) =>
  request<{ requirement_version: RequirementVersion | null }>(`/api/v0.2/projects/${projectId}/materials`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ supplemental_notes: supplementalNotes, files }),
  });
export const getRunPreflight = (projectId: number, page: RunPage, mode: RunMode, roles: string[] = [], options?: {
  templateMode?: "default" | "uploaded"; templateMappingId?: number | null; supplementalRequirements?: string;
}): Promise<RunPreflight> =>
  request(`/api/v0.2/projects/${projectId}/run-preflight`, {
    method: "POST", headers: { ...sessionHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ page, mode, roles, template_mode: options?.templateMode ?? "default",
      template_mapping_id: options?.templateMappingId ?? null,
      supplemental_requirements: options?.supplementalRequirements ?? "" }),
  });
export const runAnalysis = (projectId: number, mode: RunMode, confirmed: boolean): Promise<{ run: RunEvidence; rows: AnalysisRow[]; reused: boolean }> =>
  runRequest(projectId, "analysis-runs", { mode, confirmed });
export const runMaterialUnderstanding = (projectId: number, confirmed: boolean): Promise<{
  run: RunEvidence; understanding: MaterialUnderstanding; reused: boolean;
}> => runRequest(projectId, "material-understanding-runs", { mode: "direct", confirmed });
export const runSuggestions = (projectId: number, mode: RunMode, confirmed: boolean): Promise<{ run: RunEvidence; suggestions: Suggestion[]; reused: boolean }> =>
  runRequest(projectId, "suggestion-runs", { mode, confirmed });
export const runReview = (projectId: number, mode: RunMode, confirmed: boolean, roles: string[]): Promise<{ run: RunEvidence; suggestions: ReviewSuggestion[]; reused: boolean }> =>
  runRequest(projectId, "review-runs", { mode, confirmed, roles });
export const runCases = (projectId: number, mode: RunMode, confirmed: boolean,
  templateMode: "default" | "uploaded", templateMappingId: number | null, supplementalRequirements: string): Promise<{
    run: RunEvidence; cases: GeneratedCase[]; scope_ids: string[]; template: TemplateMappingVersion; reused: boolean;
  }> => runRequest(projectId, "case-runs", { mode, confirmed, template_mode: templateMode,
    template_mapping_id: templateMappingId, supplemental_requirements: supplementalRequirements });

const runRequest = <T,>(projectId: number, path: string, body: object): Promise<T> =>
  request(`/api/v0.2/projects/${projectId}/${path}`, {
    method: "POST", headers: { ...sessionHeaders(), "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
export const updateAnalysisSelection = (projectId: number, rowIds: string[], selected: boolean) =>
  request<{ selected_count: number; affected_count: number }>(`/api/v0.2/projects/${projectId}/analysis-selection`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ row_ids: rowIds, selected }),
  });
export const disposeSuggestion = (projectId: number, id: string, disposition: "accepted" | "rejected") =>
  request(`/api/v0.2/projects/${projectId}/suggestions/${id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ disposition }),
  });
export const disposeReviewSuggestion = (projectId: number, id: string, disposition: "accepted" | "rejected") =>
  request(`/api/v0.2/projects/${projectId}/review-suggestions/${id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ disposition }),
  });
export const skipReview = (projectId: number) => request(`/api/v0.2/projects/${projectId}/review-skip`, { method: "POST" });
export const editV020Case = (projectId: number, caseId: string, updates: object): Promise<GeneratedCase> =>
  request(`/api/v0.2/projects/${projectId}/cases/${caseId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updates),
  });
export const setV020CaseInclusion = (projectId: number, caseId: string, included: boolean): Promise<GeneratedCase> =>
  request(`/api/v0.2/projects/${projectId}/cases/${caseId}/inclusion`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ included }),
  });
export const setV020CaseRemoved = (projectId: number, caseId: string, removed: boolean): Promise<GeneratedCase> =>
  request(`/api/v0.2/projects/${projectId}/cases/${caseId}/removal`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ removed }),
  });
export const getCaseTemplate = (projectId: number): Promise<CaseTemplateState> => request(`/api/v0.2/projects/${projectId}/case-template`);
export const selectCaseTemplate = (projectId: number, mode: "default" | "uploaded", mappingId: number | null): Promise<CaseTemplateState> =>
  request(`/api/v0.2/projects/${projectId}/case-template`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, mapping_id: mappingId }),
  });
export const downloadDefaultCaseTemplate = async (projectId: number) =>
  downloadResponseFile(await fetch(`/api/v0.2/projects/${projectId}/case-template/download`), "默认测试用例模板.xlsx");
export const downloadPageResult = async (projectId: number, page: "upload" | RunPage, format: "json" | "xlsx", runId?: string) =>
  downloadResponseFile(await fetch(`/api/v0.2/projects/${projectId}/exports/${page}?format=${format}${runId ? `&run_id=${encodeURIComponent(runId)}` : ""}`), `${page}-result.${format}`);
export const downloadDeliveryPackage = async (projectId: number) =>
  downloadResponseFile(await fetch(`/api/v0.2/projects/${projectId}/delivery-package`), `project-${projectId}-delivery.zip`);
