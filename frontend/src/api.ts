export interface ProjectSettings {
  requirement_language: "zh-CN" | "en-US";
}

export interface ProjectInput {
  name: string;
  test_object: string;
  description: string;
  settings: ProjectSettings;
}

export interface Project extends ProjectInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface AssetProvenanceInput {
  name: string;
  asset_type:
    | "requirement_material"
    | "case_template"
    | "mock_output"
    | "evaluation_truth"
    | "result_input"
    | "other";
  provenance_kind: "original_synthetic" | "public_authorized" | "prohibited";
  source: string;
  usage_permission: "project_owned" | "public_license" | "prohibited" | "unknown";
  model_permission: "allowed" | "denied" | "unknown";
  requirement_version: string;
  purpose: string;
  content_base64: string;
  change_reason: string;
}

export interface AssetProvenanceRecord extends Omit<AssetProvenanceInput, "content_base64"> {
  id: number;
  project_id: number;
  revision: number;
  sha256: string;
  created_at: string;
  boundary: "original_synthetic" | "public_authorized" | "prohibited" | "unknown";
  can_enter_requirement_package: boolean;
  can_enter_model_context: boolean;
  reason: string;
}

export interface RequirementFileInput {
  asset_id: number;
  filename: string;
  media_type: string;
  content_base64: string;
}

export interface ParseDiagnostic {
  asset_id: number;
  filename: string;
  code: string;
  severity: "warning" | "error";
  message: string;
}

export interface RequirementMaterial {
  asset_id: number;
  asset_revision: number;
  filename: string;
  media_type: string;
  format: "markdown" | "text" | "json" | "yaml" | "openapi" | "docx" | "pdf" | "png" | "jpg" | "unsupported";
  sha256: string;
  content_base64: string;
  parse_status: "complete" | "partial" | "failed" | "rejected";
  fragments: Array<{
    text: string;
    source_reference: { reference_id: string; asset_id: number; filename: string; locator: string };
  }>;
  visual_inferences: Array<{
    status: "pending_confirmation";
    description: string;
    source_reference: { reference_id: string; asset_id: number; filename: string; locator: string };
  }>;
  diagnostics: ParseDiagnostic[];
}

export interface RequirementPackage {
  id: number;
  project_id: number;
  name: string;
  status: "draft" | "published";
  materials: RequirementMaterial[];
  diagnostics: ParseDiagnostic[];
  created_at: string;
  published_version_id: number | null;
}

export interface RequirementVersion {
  id: number;
  project_id: number;
  package_id: number;
  version: number;
  name: string;
  materials: RequirementMaterial[];
  diagnostics: ParseDiagnostic[];
  created_at: string;
}

export interface RequirementAnalysis {
  id: number;
  requirement_version_id: number;
  status: "draft" | "confirmed";
  atomic_requirements: Array<{
    candidate_id: string;
    stable_requirement_id: string | null;
    statement: string;
    source_reference: { locator: string; filename: string };
    decision: "pending_confirmation" | "accepted" | "rejected";
  }>;
  findings: Array<{
    finding_id: string;
    finding_type: string;
    summary: string;
    reason: string;
    status: string;
    source_reference: { locator: string; filename: string } | null;
  }>;
  visual_inferences: Array<{
    inference_id: string;
    description: string;
    source_reference: { locator: string; filename: string };
    decision: "pending_confirmation" | "accepted" | "rejected";
  }>;
  confirmed_by: string | null;
}

export interface AIRun {
  id: number;
  task_type: string;
  prompt_version: string;
  status: "succeeded" | "validation_failed" | "failed";
  validation_status: "passed" | "failed" | "not_run";
  is_mock: boolean;
  attempts: Array<{ attempt: number; status: string; error_code: string | null }>;
  disposition: { decision: string; reason: string } | null;
}

export interface TestDesign {
  id: number;
  requirement_version_id: number;
  status: "draft" | "confirmed";
  dimensions: Array<{ id: string; name: string; status: "active" | "inactive" }>;
  scope_items: Array<{ id: string; title: string; primary_dimension_id: string }>;
  risks: Array<{
    scope_item_id: string;
    final_score: number;
    risk_level: string;
    priority: string;
    factors: Array<{ key: string; name: string; score: number; weight: number; source_references: unknown[] }>;
  }>;
  automation_candidates: Array<{
    scope_item_id: string;
    suggested_score: number;
    decision: string;
    suggestion_reason: string;
    factors: {
      regression_value: number;
      determinism: number;
      environment_control: number;
      saving_benefit: number;
      maintenance_cost: number;
      manual_observation: number;
    };
  }>;
  confirmed_by: string | null;
}

export interface TemplateColumn {
  index: number;
  name: string;
  sample_values: string[];
}

export interface TemplateSheet {
  name: string;
  index: number;
  role_suggestion: "case" | "instruction" | "dictionary" | "statistics" | "unknown";
  role: "case" | "instruction" | "dictionary" | "statistics" | "unknown";
  title_row_candidates: number[];
  title_row: number | null;
  columns: TemplateColumn[];
  participates: boolean;
  field_mapping: Record<string, string>;
  diagnostics: Array<{ code: string; severity: "warning" | "error"; message: string }>;
}

export interface TemplateMappingVersion {
  id: number;
  project_id: number;
  version: number;
  filename: string;
  format: "xlsx" | "csv";
  status: "draft" | "confirmed";
  sheets: TemplateSheet[];
  diagnostics: Array<{ code: string; severity: "warning" | "error"; message: string }>;
  retained_sheet_names: string[];
  confirmed_by: string | null;
}

export interface CandidateTestCase {
  id: string;
  title: string;
  objective: string;
  variant: string;
  preconditions: string[];
  steps: Array<{ order: number; action: string; input: string; expected: string }>;
  overall_expectation: string;
  evidence_requirements: string[];
  requirement_ids: string[];
  requirement_references: unknown[];
  scope_item_id: string;
  risk_item_id: string;
  priority: string;
  case_sheet_name: string;
  automation_mapping: string | null;
  unexpressed_fields: string[];
  design_basis: Array<{ method: string; reason: string }>;
}

export interface CaseGeneration {
  id: number;
  ai_run_id: number;
  ai_run_status: string;
  is_mock: boolean;
  status: "succeeded" | "empty" | "validation_failed" | "failed" | "needs_confirmation";
  template_diagnostics: Array<{ code: string; message: string }>;
  candidates: CandidateTestCase[];
}

export interface CaseReviewSuggestion {
  id: string;
  candidate_id: string;
  role: "product_manager" | "test_manager" | "project_manager";
  suggestion_type: string;
  summary: string;
  rationale: string;
  source_references: unknown[];
  limitations: string[];
  disposition: "accepted" | "rejected" | "modified" | null;
}

export interface CaseReviewBatch {
  id: number;
  generation_id: number;
  status: "in_progress" | "completed" | "confirmed";
  reviewer_runs: Array<{ role: string; ai_run_id: number }>;
  suggestions: CaseReviewSuggestion[];
  groups: Array<{ id: string; summary: string; original_suggestion_ids: string[]; source_roles: string[] }>;
  revisions: Array<{
    id: string;
    candidate_id: string;
    revision: number;
    stable_case_id: string | null;
    lifecycle_status: "draft" | "effective" | "closed" | "deprecated" | "superseded";
    participation_status: "included" | "not_included" | "pending_impact" | "pending_retest";
  }>;
  inclusion: Record<string, boolean>;
  confirmed_by: string | null;
}

export interface TestTask {
  contract_version: "test-task.v1";
  task_id: string;
  task_version: number;
  project_id: number;
  case_review_batch_id: number;
  execution_scope: "selected";
  execution_target:
    | "manual" | "test_execution_diagnostics" | "generic_automation" | "external_executor" | "unspecified";
  cases: Array<{
    stable_case_id: string;
    case_revision_id: string;
    case_revision: number;
    external_case_number?: string | null;
    title: string;
    priority: "P0" | "P1" | "P2" | "P3";
    preconditions: string[];
    parameters: Record<string, string>;
    steps: Array<Record<string, string | number>>;
    expected_result: string;
    verdict_method: "expected_result_match" | "manual_observation" | "adapter_defined";
    evidence_requirements: string[];
  }>;
  published_by: string;
  published_at: string;
}

export interface ExecutionBatch {
  id: number;
  project_id: number;
  test_task_id: string;
  test_task_version: number;
  product_version: string;
  requirement_version_id: number;
  environment: string;
  scope: string;
  responsible_person: string;
  execution_target: string;
  cases: Array<{
    stable_case_id: string;
    case_revision_id: string;
    case_revision: number;
    external_case_number: string | null;
    lifecycle_status: "effective" | "closed" | "deprecated" | "superseded";
    participation_status: "included" | "not_included" | "pending_impact" | "pending_retest";
    execution_sequence: number;
    display_number: string;
    title: string;
  }>;
  manual_file_format: "csv";
  created_at: string;
}

export type ExecutionResultStatus =
  | "passed" | "execution_failed" | "blocked" | "not_executed" | "execution_error";

export interface ExecutionResultRecord {
  id: number;
  batch_id: number;
  source_type: "manual" | "test_execution_diagnostics" | "generic_automation";
  source_record_id: string;
  stable_case_id: string | null;
  case_revision_id: string | null;
  execution_sequence: number | null;
  status: ExecutionResultStatus;
  actual_result: string;
  reason: string;
  executor: string;
  evidence_references: string[];
  match_status: "matched" | "unresolved" | "rejected";
  retest_of_result_id: number | null;
}

export interface ExecutionBatchResults {
  batch_id: number;
  records: ExecutionResultRecord[];
  unresolved_records: ExecutionResultRecord[];
  conflicts: Array<{
    id: number;
    result_ids: number[];
    statuses: Record<string, ExecutionResultStatus>;
    status: "open" | "resolved";
    decision: ExecutionResultStatus | null;
    rationale: string | null;
    confirmed_by: string | null;
  }>;
  case_summaries: Array<{
    stable_case_id: string;
    initial_result: ExecutionResultRecord | null;
    latest_result: ExecutionResultRecord | null;
    history: ExecutionResultRecord[];
  }>;
  conclusion: { conclusion: ExecutionResultStatus; rationale: string; confirmer_name: string } | null;
}

export interface CoverageMetric {
  label: string;
  numerator: number;
  denominator: number;
  percentage: number;
  covered_items: string[];
  uncovered_items: string[];
  high_risk_gaps: string[];
  quality_issues: Array<{ id: number; phenomenon: string; severity: string }>;
  execution_evidence: Array<{ id: number; stable_case_id: string | null; evidence_references: string[] }>;
}

export interface CoverageSummary {
  metrics: Record<string, CoverageMetric>;
}

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
export const createRequirementReview = (projectId: number, versionId: number): Promise<RequirementAnalysis> =>
  request(`/api/projects/${projectId}/requirement-versions/${versionId}/requirement-review`, { method: "POST" });
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
): Promise<CaseGeneration> => request(
  `/api/projects/${projectId}/test-designs/${designId}/case-generations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      template_mapping_id: templateMappingId,
      accept_template_limitations: acceptTemplateLimitations,
      variants: ["normal", "boundary", "invalid"],
    }),
  },
);

export const createCaseReviews = (
  projectId: number, generationId: number,
): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-generations/${generationId}/reviews`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
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
): Promise<CaseReviewBatch> => request(
  `/api/projects/${projectId}/case-review-batches/${batchId}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmer_name: confirmerName, inclusion: Object.fromEntries(
      candidateIds.map((candidateId) => [candidateId, true]),
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

const toTemplateMapping = (sheet: TemplateSheet) => ({
  sheet_name: sheet.name, role: sheet.role, participates: sheet.participates,
  title_row: sheet.title_row, field_mapping: sheet.field_mapping,
});
