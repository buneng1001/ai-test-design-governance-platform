// 项目领域请求。
import { request } from "./api_client";
import type { Project, ProjectInput } from "./api_types";

export const listProjects = (): Promise<Project[]> => request("/api/projects");
export const getProject = (projectId: number): Promise<Project> => request(`/api/projects/${projectId}`);
export const createProject = (project: ProjectInput): Promise<Project> => request("/api/projects", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(project),
});
export const updateProject = (projectId: number, project: ProjectInput): Promise<Project> => request(
  `/api/projects/${projectId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(project),
  },
);
