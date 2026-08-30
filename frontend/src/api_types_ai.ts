// AI 配置与运行记录领域的 API 类型。
export type ModelProviderId = "deepseek" | "siliconflow" | "kimi" | "glm" | "custom";
export interface ModelProviderOption { id: ModelProviderId; name: string; base_url: string; models: string[]; }
export interface SessionModelConfig { provider: ModelProviderId; model: string; base_url: string; api_key: string; }
export interface SessionModelConfigStatus extends Omit<SessionModelConfig, "api_key"> { api_key_configured: boolean; }
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
