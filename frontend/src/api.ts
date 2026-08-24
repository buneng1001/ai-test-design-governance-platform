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
export const listAIRuns = (projectId: number): Promise<AIRun[]> => request(`/api/projects/${projectId}/ai-runs`);
