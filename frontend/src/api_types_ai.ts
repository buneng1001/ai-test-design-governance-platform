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
  source?: "mock" | "real" | "template";
  stage?: string;
  batch_number?: number;
  batch_total?: number;
  completed_count?: number;
  total_count?: number;
  estimated_remaining_ms?: number | null;
  recovery_point?: string | null;
  attempts: Array<{ attempt: number; status: string; error_code: string | null; diagnostic?: string | null;
    error_category?: string | null; retry_after_ms?: number | null; recovery_point?: string | null }>;
  disposition: { decision: string; reason: string } | null;
}

/** 后端持久化的工作流运行控制记录；输入摘要不由客户端填写。 */
export interface AIRunControl {
  id: string;
  project_id: number;
  workflow: "requirement_analysis" | "case_generation";
  input_fingerprint: string;
  status: "running" | "stopped" | "completed";
  next_batch: number;
  batch_total: number;
  completed_count: number;
  final_asset_type: string | null;
  final_asset_id: number | null;
}

export const isAIRunControl = (value: unknown): value is AIRunControl => typeof value === "object"
  && value !== null && "workflow" in value && "next_batch" in value && "completed_count" in value;
