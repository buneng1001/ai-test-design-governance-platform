// AI 模型配置与运行记录请求。
import { request, sessionHeaders } from "./api_client";
import type { AIRun, ModelProviderId, ModelProviderOption, SessionModelConfig,
  SessionModelConfigStatus } from "./api_types";

export const readStoredSessionModelConfig = (): SessionModelConfig | null => {
  const saved = sessionStorage.getItem("ai-test-design-model-config");
  return saved ? JSON.parse(saved) as SessionModelConfig : null;
};
export const listModelProviders = (): Promise<ModelProviderOption[]> => request("/api/model-providers");
export const getSessionModelConfig = async (): Promise<SessionModelConfigStatus | null> => {
  const config = readStoredSessionModelConfig();
  if (config) return { provider: config.provider, model: config.model, base_url: config.base_url,
    api_key_configured: true };
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
export const listAIRuns = (projectId: number): Promise<AIRun[]> => request(`/api/projects/${projectId}/ai-runs`);
