import { request } from "./api_client";
import type { ProjectWorkflowView } from "./api_types";

export const getProjectWorkflow = (projectId: number): Promise<ProjectWorkflowView> =>
  request(`/api/projects/${projectId}/workflow`);
