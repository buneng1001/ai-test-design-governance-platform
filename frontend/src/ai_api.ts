// AI 模型配置与运行记录请求。
import { request, sessionHeaders } from "./api_client";
import type { AIRun, ConnectionTestResult, ModelDiscoveryResult, ModelProviderOption, SessionModelConfig,
  SessionModelConfigStatus } from "./api_types";

export const listModelProviders = (): Promise<ModelProviderOption[]> => request("/api/model-providers");
export const getSessionModelConfig = (): Promise<SessionModelConfigStatus | null> =>
  request("/api/ai-session-config", { headers: sessionHeaders() });
export const saveSessionModelConfig = (config: SessionModelConfig): Promise<SessionModelConfigStatus> =>
  request<SessionModelConfigStatus>("/api/ai-session-config", {
    method: "PUT", headers: { ...sessionHeaders(), "Content-Type": "application/json" }, body: JSON.stringify(config),
  });
export const discoverSessionModels = (config: SessionModelConfig): Promise<ModelDiscoveryResult> =>
  request("/api/ai-session-config/models/discover", {
    method: "POST", headers: { ...sessionHeaders(), "Content-Type": "application/json" }, body: JSON.stringify(config),
  });
export const testSessionModelConfig = (config: SessionModelConfig): Promise<ConnectionTestResult> =>
  request("/api/ai-session-config/test", {
  method: "POST", headers: { ...sessionHeaders(), "Content-Type": "application/json" }, body: JSON.stringify(config),
});
export const clearSessionModelConfig = async (): Promise<void> => {
  const response = await fetch("/api/ai-session-config", { method: "DELETE", headers: sessionHeaders() });
  if (!response.ok) throw new Error("清除模型配置失败");
};
export const listAIRuns = (projectId: number): Promise<AIRun[]> => request(`/api/projects/${projectId}/ai-runs`);
