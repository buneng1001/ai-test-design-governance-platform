export interface ProjectSettings {
  requirement_language: "zh-CN" | "en-US";
}

export interface ProjectInput {
  name: string;
  test_object: string;
  software_version: string;
  description: string;
  settings: ProjectSettings;
}

export interface Project extends ProjectInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export type ModelProviderId = "deepseek" | "siliconflow" | "kimi" | "glm" | "custom";
export interface ModelProviderOption { id: ModelProviderId; name: string; base_url: string; models: string[]; }
export interface SessionModelConfig { provider: ModelProviderId; model: string; base_url: string; api_key: string; }
export interface SessionModelConfigStatus extends Omit<SessionModelConfig, "api_key"> { api_key_configured: boolean; }
export const readStoredSessionModelConfig = (): SessionModelConfig | null => {
  const saved = sessionStorage.getItem("ai-test-design-model-config");
  return saved ? JSON.parse(saved) as SessionModelConfig : null;
};

import type { AssetProvenanceInput, AssetProvenanceRecord, RequirementFileInput, ParseDiagnostic, RequirementMaterial, RequirementPackage, RequirementVersion, RequirementAnalysis, AIRun, TestDesign, TemplateColumn, TemplateSheet, TemplateMappingVersion, CandidateTestCase, CaseGeneration, CaseReviewSuggestion, CaseReviewBatch, TestTask, ExecutionBatch, ExecutionResultStatus, ExecutionResultRecord, ExecutionBatchResults, CoverageMetric, CoverageSummary, ChangeImpactAnalysis, RegressionCandidate, RegressionSelection, ReportDocument } from "./api_types";

export type { AssetProvenanceInput, AssetProvenanceRecord, RequirementFileInput, ParseDiagnostic, RequirementMaterial, RequirementPackage, RequirementVersion, RequirementAnalysis, AIRun, TestDesign, TemplateColumn, TemplateSheet, TemplateMappingVersion, CandidateTestCase, CaseGeneration, CaseReviewSuggestion, CaseReviewBatch, TestTask, ExecutionBatch, ExecutionResultStatus, ExecutionResultRecord, ExecutionBatchResults, CoverageMetric, CoverageSummary, ChangeImpactAnalysis, RegressionCandidate, RegressionSelection, ReportDocument } from "./api_types";
interface ValidationError {
  loc?: unknown[];
  type?: string;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = formatErrorDetail(body?.detail);
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

const fieldLabels: Record<string, string> = {
  name: "项目名称",
  test_object: "测试对象",
  description: "项目描述",
  requirement_language: "需求资料默认语言",
};

function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return "请求未完成，请检查填写内容";
  return detail.map((error: ValidationError) => {
    const field = String(error.loc?.at(-1) ?? "项目字段");
    const label = fieldLabels[field] ?? field;
    if (error.type === "string_too_long") return `${label}超过长度限制`;
    if (error.type === "missing") return `${label}为必填项`;
    return `${label}填写不正确`;
  }).join("；");
}

export const listProjects = (): Promise<Project[]> => request("/api/projects");
export const getProject = (projectId: number): Promise<Project> => request(`/api/projects/${projectId}`);
export const createProject = (project: ProjectInput): Promise<Project> => request("/api/projects", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(project),
});
export const updateProject = (projectId: number, project: ProjectInput): Promise<Project> =>
  request(`/api/projects/${projectId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  });
const sessionId = (): string => {
  const key = "ai-test-design-session-id";
  const existing = sessionStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  sessionStorage.setItem(key, created);
  return created;
};
const sessionHeaders = (): HeadersInit => ({ "X-Session-ID": sessionId() });
export const listModelProviders = (): Promise<ModelProviderOption[]> => request("/api/model-providers");
export const getSessionModelConfig = async (): Promise<SessionModelConfigStatus | null> => {
  const config = readStoredSessionModelConfig();
  if (config) {
    return { provider: config.provider, model: config.model, base_url: config.base_url, api_key_configured: true };
  }
  return request("/api/ai-session-config", { headers: sessionHeaders() });
};
export const saveSessionModelConfig = async (config: SessionModelConfig): Promise<SessionModelConfigStatus> => {
  const saved = await request<SessionModelConfigStatus>("/api/ai-session-config", {
    method: "PUT", headers: { ...sessionHeaders(), "Content-Type": "application/json" }, body: JSON.stringify(config),
  });
  sessionStorage.setItem("ai-test-design-model-config", JSON.stringify(config));
  return saved;
};
export const testSessionModelConfig = (config: SessionModelConfig): Promise<{
  success: boolean; message: string; provider: ModelProviderId; model: string;
}> => request("/api/ai-session-config/test", {
  method: "POST", headers: { ...sessionHeaders(), "Content-Type": "application/json" }, body: JSON.stringify(config),
});
export const clearSessionModelConfig = async (): Promise<void> => {
  const response = await fetch("/api/ai-session-config", { method: "DELETE", headers: sessionHeaders() });
  if (!response.ok) throw new Error("清除模型配置失败");
  sessionStorage.removeItem("ai-test-design-model-config");
};
export const listAssets = (projectId: number): Promise<AssetProvenanceRecord[]> =>
  request(`/api/projects/${projectId}/assets`);
export const createAsset = (
  projectId: number,
  asset: AssetProvenanceInput,
): Promise<AssetProvenanceRecord> => request(`/api/projects/${projectId}/assets`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(asset),
});
export const createRequirementPackage = (
  projectId: number,
  name: string,
  files: RequirementFileInput[],
): Promise<RequirementPackage> => request(`/api/projects/${projectId}/requirement-packages`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name, files }),
});
export const publishRequirementPackage = (
  projectId: number,
  packageId: number,
): Promise<RequirementVersion> => request(
  `/api/projects/${projectId}/requirement-packages/${packageId}/publish`,
  { method: "POST" },
);
export const listRequirementVersions = (projectId: number): Promise<RequirementVersion[]> =>
  request(`/api/projects/${projectId}/requirement-versions`);
export const createRequirementReview = (
  projectId: number, versionId: number, mode: "mock" | "real" = "mock",
): Promise<RequirementAnalysis> => request(
  `/api/projects/${projectId}/requirement-versions/${versionId}/requirement-review`, {
    method: "POST", headers: sessionHeaders(), body: JSON.stringify({ mode }),
  },
);
export const updateAtomicRequirement = (
  projectId: number,
  analysisId: number,
  candidateId: string,
  input: { decision: "accepted" | "rejected"; statement?: string },
): Promise<RequirementAnalysis> => request(
  `/api/projects/${projectId}/requirement-reviews/${analysisId}/atomic-requirements/${candidateId}`,
  { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) },
);
export const updateFinding = (
  projectId: number,
  analysisId: number,
  findingId: string,
  status: string,
): Promise<RequirementAnalysis> => request(
  `/api/projects/${projectId}/requirement-reviews/${analysisId}/findings/${findingId}`,
  { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) },
);
export const updateVisualInference = (
  projectId: number,
  analysisId: number,
  inferenceId: string,
  decision: "accepted" | "rejected",
): Promise<RequirementAnalysis> => request(
  `/api/projects/${projectId}/requirement-reviews/${analysisId}/visual-inferences/${inferenceId}`,
  { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) },
);
export const confirmRequirementReview = (
  projectId: number,
  analysisId: number,
  confirmerName: string,
): Promise<RequirementAnalysis> => request(
  `/api/projects/${projectId}/requirement-reviews/${analysisId}/confirm`,
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmer_name: confirmerName }),
  },
);
export const updateRequirementSelection = (
  projectId: number, analysisId: number, selectedRequirementIds: string[],
): Promise<RequirementAnalysis> => request(
  `/api/projects/${projectId}/requirement-reviews/${analysisId}/selection`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected_requirement_ids: selectedRequirementIds }),
  },
);
export const decideRequirementConflict = (
  projectId: number, analysisId: number, conflictId: string,
  decision: RequirementAnalysis["conflicts"][number]["decision"], confirmerName: string,
): Promise<RequirementAnalysis> => request(
  `/api/projects/${projectId}/requirement-reviews/${analysisId}/conflicts/${conflictId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, confirmer_name: confirmerName }),
  },
);
export const listAIRuns = (projectId: number): Promise<AIRun[]> => request(`/api/projects/${projectId}/ai-runs`);
export const createTestDesign = (projectId: number, versionId: number): Promise<TestDesign> => request(
  `/api/projects/${projectId}/requirement-versions/${versionId}/test-designs`,
  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) },
);
export const confirmTestDesign = (
  projectId: number,
  designId: number,
  confirmerName: string,
): Promise<TestDesign> => request(`/api/projects/${projectId}/test-designs/${designId}/confirm`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ confirmer_name: confirmerName }),
});
export const addTestDimension = (projectId: number, designId: number, name: string): Promise<TestDesign> => request(
  `/api/projects/${projectId}/test-designs/${designId}/dimensions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  },
);
export const adjustTestRisk = (
  projectId: number, designId: number, scopeItemId: string, factors: TestDesign["risks"][number]["factors"],
): Promise<TestDesign> => request(`/api/projects/${projectId}/test-designs/${designId}/risks/${scopeItemId}`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ factors, adjustment_reason: "测试工程师在页面确认风险因子" }),
});
export const decideAutomation = (
  projectId: number, designId: number, scopeItemId: string,
  factors: TestDesign["automation_candidates"][number]["factors"], decision: string,
): Promise<TestDesign> => request(`/api/projects/${projectId}/test-designs/${designId}/automation/${scopeItemId}`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ factors, decision, decision_reason: "测试工程师在页面确认自动化决定" }),
});

export const uploadTemplate = (
  projectId: number, filename: string, contentBase64: string,
): Promise<TemplateMappingVersion> => request(`/api/projects/${projectId}/template-mappings`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ filename, content_base64: contentBase64 }),
});

export const confirmTemplate = (
  projectId: number, mappingId: number, confirmerName: string, mappings: TemplateSheet[],
): Promise<TemplateMappingVersion> => request(
  `/api/projects/${projectId}/template-mappings/${mappingId}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmer_name: confirmerName, mappings: mappings.map(toTemplateMapping) }),
  },
);

export const validateTemplate = (
  projectId: number, mappingId: number, confirmerName: string, mappings: TemplateSheet[],
): Promise<{ valid: boolean; diagnostics: TemplateSheet["diagnostics"] }> => request(
  `/api/projects/${projectId}/template-mappings/${mappingId}/validate`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmer_name: confirmerName, mappings: mappings.map(toTemplateMapping) }),
  },
);

export const generateCases = (
  projectId: number,
  designId: number,
  templateMappingId: number,
  acceptTemplateLimitations = false,
  strictConflicts = false,
  modules: string[] = [],
  mode: "mock" | "real" = "mock",
): Promise<CaseGeneration> => request(
  `/api/projects/${projectId}/test-designs/${designId}/case-generations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...(templateMappingId > 0 ? { template_mapping_id: templateMappingId } : {}),
      accept_template_limitations: acceptTemplateLimitations,
      variants: ["normal", "boundary", "invalid"],
      strict_conflicts: strictConflicts,
      modules,
      mode,
    }),
  },
);

export const createCaseReviews = (
  projectId: number, generationId: number, mode: "mock" | "real" = "mock",
): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-generations/${generationId}/reviews`, {
    method: "POST", headers: { ...sessionHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  },
);

export const disposeCaseReviewSuggestion = (
  projectId: number, batchId: number, suggestionId: string, decision: "accepted" | "rejected" | "modified",
  modifiedFields: Record<string, string> = {},
): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/suggestions/${suggestionId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision,
      reason: `测试工程师${decision === "accepted" ? "采纳" : decision === "rejected" ? "拒绝" : "修改并采纳"}该建议`,
      modified_fields: modifiedFields,
    }),
  },
);

export const confirmCaseReviews = (
  projectId: number, batchId: number, candidateIds: string[], confirmerName: string,
  excludedCandidateIds: string[] = [],
): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmer_name: confirmerName, inclusion: Object.fromEntries(
      candidateIds.map((candidateId) => [candidateId, !excludedCandidateIds.includes(candidateId)]),
    ) }),
  },
);

export const changeCaseStatus = (
  projectId: number,
  batchId: number,
  stableCaseId: string,
  lifecycleStatus: CaseReviewBatch["revisions"][number]["lifecycle_status"],
  participationStatus: CaseReviewBatch["revisions"][number]["participation_status"],
): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/cases/${stableCaseId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lifecycle_status: lifecycleStatus,
      participation_status: participationStatus,
      reason: "测试工程师更新用例状态",
      confirmer_name: "测试工程师",
    }),
  },
);

export const editCase = (
  projectId: number, batchId: number, caseId: string, fields: Record<string, unknown>,
): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/cases/${caseId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  },
);

export const changeCaseStatuses = (
  projectId: number, batchId: number, stableCaseIds: string[], participationStatus: "included" | "not_included",
): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/cases/bulk-status`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      stable_case_ids: stableCaseIds, participation_status: participationStatus,
      reason: participationStatus === "included" ? "恢复纳入本次用例集" : "移除出本次用例集",
      confirmer_name: "测试工程师",
    }),
  },
);

export const exportCaseFile = async (
  projectId: number,
  batchId: number,
  scope: "all" | "selected" | "changed" = "all",
  stableCaseIds: string[] = [],
): Promise<void> => {
  const response = await fetch(`/api/projects/${projectId}/case-review-batches/${batchId}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope, stable_case_ids: stableCaseIds }),
  });
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const disposition = response.headers.get("content-disposition");
  link.download = disposition?.match(/filename="([^"]+)"/)?.[1] ?? "test-cases.csv";
  link.click();
  URL.revokeObjectURL(url);
};

export const publishTestTask = (
  projectId: number,
  batchId: number,
  input: {
    confirmer_name: string;
    execution_target: TestTask["execution_target"];
    stable_case_ids: string[];
    target_extension: Record<string, string>;
  },
): Promise<TestTask> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/test-tasks`,
  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) },
);

export const createExecutionBatch = (
  projectId: number,
  taskId: string,
  input: {
    product_version: string;
    requirement_version_id: number;
    environment: string;
    scope: string;
    responsible_person: string;
    stable_case_ids: string[];
  },
): Promise<ExecutionBatch> => request(
  `/api/projects/${projectId}/test-tasks/${taskId}/execution-batches`,
  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) },
);

export const downloadManualExecutionFile = async (projectId: number, batchId: number): Promise<void> => {
  const response = await fetch(`/api/projects/${projectId}/execution-batches/${batchId}/manual-file`);
  if (!response.ok) throw new Error(await response.text());
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = response.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1]
    ?? `execution-batch-${batchId}.csv`;
  link.click();
  URL.revokeObjectURL(url);
};

export const importExecutionResults = (
  projectId: number,
  batchId: number,
  sourceType: "manual" | "test_execution_diagnostics" | "generic_automation",
  results: Array<Record<string, unknown>>,
): Promise<ExecutionBatchResults> => request(
  `/api/projects/${projectId}/execution-batches/${batchId}/results/import`,
  {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_type: sourceType, results }),
  },
);

export const resolveExecutionConflict = async (
  projectId: number,
  batchId: number,
  conflictId: number,
  decision: ExecutionResultStatus,
  rationale: string,
  confirmerName: string,
): Promise<ExecutionBatchResults["conflicts"][number]> => {
  await request<ExecutionBatchResults["conflicts"][number]>(
    `/api/projects/${projectId}/execution-batches/${batchId}/conflicts/${conflictId}/resolve`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, rationale, confirmer_name: confirmerName }),
    },
  );
  const summary = await getExecutionResults(projectId, batchId);
  const conflict = summary.conflicts.find((item) => item.id === conflictId);
  if (!conflict) throw new Error("结果冲突不存在");
  return conflict;
};

export const getExecutionResults = (projectId: number, batchId: number): Promise<ExecutionBatchResults> => request(
  `/api/projects/${projectId}/execution-batches/${batchId}/results`,
);

export const confirmExecutionConclusion = (
  projectId: number, batchId: number, conclusion: ExecutionResultStatus, rationale: string, confirmerName: string,
): Promise<ExecutionBatchResults> => request(
  `/api/projects/${projectId}/execution-batches/${batchId}/conclusion`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conclusion, rationale, confirmer_name: confirmerName }),
  },
);

export const getCoverage = (
  projectId: number,
  requirementVersionId: number,
  designId: number,
  caseReviewBatchId: number,
  executionBatchId?: number,
): Promise<CoverageSummary> => {
  const params = new URLSearchParams({
    requirement_version_id: String(requirementVersionId),
    design_id: String(designId),
    case_review_batch_id: String(caseReviewBatchId),
  });
  if (executionBatchId) params.set("execution_batch_id", String(executionBatchId));
  return request(`/api/projects/${projectId}/coverage?${params.toString()}`);
};

export const createChangeImpact = (
  projectId: number, baseVersionId: number, targetVersionId: number,
): Promise<ChangeImpactAnalysis> => request(`/api/projects/${projectId}/change-impact-analyses`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ base_version_id: baseVersionId, target_version_id: targetVersionId }),
});

export const confirmChangeImpact = (
  projectId: number, analysisId: number, changes: ChangeImpactAnalysis["changes"],
): Promise<ChangeImpactAnalysis> => request(`/api/projects/${projectId}/change-impact-analyses/${analysisId}/confirm`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ confirmer_name: "测试工程师", decisions: Object.fromEntries(
    changes.map((change) => [change.id, "confirmed"]),
  ) }),
});

export const createRegressionSelection = (projectId: number, analysisId: number): Promise<RegressionSelection> =>
  request(`/api/projects/${projectId}/change-impact-analyses/${analysisId}/regression-selection`, { method: "POST" });

export const confirmRegressionSelection = (
  projectId: number, selection: RegressionSelection,
): Promise<RegressionSelection> => request(
  `/api/projects/${projectId}/regression-selections/${selection.id}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmer_name: "测试工程师", decisions: Object.fromEntries(
      selection.candidates.map((candidate) => [candidate.stable_case_id, true]),
    ) }),
  },
);

export const getAuditPackage = (projectId: number): Promise<ReportDocument> =>
  request(`/api/projects/${projectId}/reports/audit-package`);

const toTemplateMapping = (sheet: TemplateSheet) => ({
  sheet_name: sheet.name, role: sheet.role, participates: sheet.participates,
  title_row: sheet.title_row, field_mapping: sheet.field_mapping,
});
