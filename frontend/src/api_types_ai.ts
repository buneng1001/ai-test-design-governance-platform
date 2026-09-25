// AI 配置与运行记录领域的 API 类型。
export type ModelProviderId = "deepseek" | "siliconflow" | "kimi" | "glm" | "custom";
export type ModelState = "preset" | "discovered" | "verified" | "failed" | "invalidated" | "manual";
export interface ModelOption { id: string; state: ModelState; }
export interface ModelProviderOption { id: ModelProviderId; name: string; base_url: string; models: ModelOption[]; }
export interface SessionModelConfig {
  provider: ModelProviderId; model: string; base_url: string; api_key: string; remember_api_key: boolean;
}
export interface SessionModelConfigStatus {
  provider: ModelProviderId; model: string; base_url: string; credential_source: string;
  credential_configured: boolean; model_options: ModelOption[];
  verification_status: "unverified" | "verified" | "failed" | "invalidated";
  validated_at: string | null;
}
export interface ModelServiceError {
  stage: "connection_test" | "model_discovery" | "model_call"; provider: string; model: string;
  error_type: string; retryable: boolean; user_message: string; suggested_action: string; detail: string | null;
}
export interface ConnectionTestResult {
  success: boolean; message: string | null; provider: ModelProviderId; model: string; error: ModelServiceError | null;
}
export interface ModelDiscoveryResult {
  success: boolean; provider: ModelProviderId; models: ModelOption[]; error: ModelServiceError | null;
}
export interface AIRun {
  id: number;
  task_type: string;
  prompt_version: string;
  status: "succeeded" | "validation_failed" | "failed";
  validation_status: "passed" | "failed" | "not_run";
  is_mock: boolean;
  attempts: Array<{ attempt: number; status: string; error_code: string | null; diagnostic?: string | null }>;
  disposition: { decision: string; reason: string } | null;
}
