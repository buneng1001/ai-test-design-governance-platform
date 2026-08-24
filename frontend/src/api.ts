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

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string" ? body.detail : "请求未完成，请检查填写内容";
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
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
