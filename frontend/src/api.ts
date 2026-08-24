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
  asset_type: string;
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
  can_enter_formal_package: boolean;
  can_enter_model_context: boolean;
  reason: string;
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
