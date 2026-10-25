import type { RequirementPackage, RequirementVersion, TemplateMappingVersion } from "./api_types";

export type RunMode = "direct" | "skill" | "local";
export type RunPage = "understanding" | "analysis" | "suggestions" | "review" | "cases";

export interface ProjectSummary {
  id: number; name: string; test_object: string; software_version: string; updated_at: string;
  archived_at: string | null; current_requirement_version: number | null;
  latest_analysis_status: string; latest_case_status: string; latest_export_at: string | null;
}

export interface CostAvailability { status: "available" | "unavailable"; reason?: string; amount?: number; currency?: string; }
export interface UsageAvailability {
  status: "available" | "unavailable"; reason?: string; input_tokens?: number | null;
  output_tokens?: number | null; total_tokens?: number | null;
}
export interface RunEvidence {
  id: string; project_id: number; page: RunPage; mode: RunMode; status: "running" | "completed" | "failed" | "stopped";
  source_label: string; provider: string; model: string; model_endpoint?: string; credential_source: string;
  input_summary: { file_count: number; fragment_count: number; analysis_row_count: number;
    source_fragment_count?: number; context_chunk_count?: number; selected_row_count: number;
    requirement_version_id: number; roles: string[]; material_understanding_used?: boolean;
    material_understanding_run_id?: string | null };
  prompt_version: string; skill_version: string | null; estimated_input_tokens: number; max_output_tokens: number;
  request_count?: number;
  workflow_stage_count?: number;
  max_request_input_tokens?: number;
  max_total_output_tokens?: number;
  model_timeout_seconds?: number | null;
  timeout_policy?: { response_start_seconds: number; stream_idle_seconds: number; request_total_seconds: number } | null;
  supplemental_notes: string; supplemental_requirements: string; template_filename: string | null;
  estimated_cost: CostAvailability; actual_usage: UsageAvailability | null; actual_cost: CostAvailability | null;
  stage: string; stage_events: Array<{ stage: string; status: string; detail: string }>;
  duration_ms: number | null; started_at: string; completed_at: string | null; error: string | null;
  next_step: string; result_summary: { count: number; label: string } | null;
  reused?: boolean; cancel_requested?: boolean;
  progress?: { completed_units: number; total_units: number; stage: string };
  attempts?: Array<{ unit: number; stage_id?: string; attempt: number; error_code?: string | null;
    duration_ms?: number | null; first_event_ms?: number | null; finish_reason?: string | null;
    response_length?: number | null; diagnostic?: string | null }>;
  role_reports?: Array<{ role: string; summary: string; strengths: string[]; concerns: string[] }>;
}
export interface RunPreflight {
  page: RunPage; mode: RunMode; provider: string; model: string; model_endpoint?: string; credential_source: string;
  verification_status: string; input_summary: RunEvidence["input_summary"]; supplemental_notes: string;
  supplemental_requirements: string; template_filename: string | null;
  prompt_version: string; skill_version: string | null; estimated_input_tokens: number; max_output_tokens: number;
  request_count?: number;
  workflow_stage_count?: number;
  max_request_input_tokens?: number;
  max_total_output_tokens?: number;
  model_timeout_seconds?: number | null;
  timeout_policy?: { response_start_seconds: number; stream_idle_seconds: number; request_total_seconds: number } | null;
  estimated_cost: CostAvailability; requires_confirmation: boolean;
}
export interface CaseGenerationRecord {
  id: string; project_id: number; run_id: string; scope_ids: string[];
  template: TemplateMappingVersion; supplemental_requirements: string; created_at: string;
}
export interface AnalysisRow {
  id: string; project_id: number; run_id: string; module: string; function_point: string; test_item: string;
  test_point: string; source_reference_id: string; source: string; source_reference: Record<string, unknown>;
  ai_reason: string; information_gap: string; status: "ready" | "needs_information"; selected: boolean;
  origin: "analysis" | "suggestion" | "review"; mode: string;
  total_index: number; test_basis: string; test_source: string; test_type: string;
  priority: "P0" | "P1" | "P2" | "P3"; related_requirement_id: string;
}
export interface MaterialUnderstandingFragment {
  source_reference_id: string; title: string; summary: string; key_points: string[];
  constraints: string[]; ambiguities: string[];
  source_reference: { filename?: string; locator?: string; [key: string]: unknown };
}
export interface MaterialUnderstanding {
  run_id: string; requirement_version_id: number; overview: string;
  organized_fragments: MaterialUnderstandingFragment[];
}
export interface Suggestion {
  id: string; project_id: number; run_id: string; suggestion_action: "add" | "remove" | "risk";
  module: string; test_item: string; test_basis: string; test_source: string; test_type: string; priority: string;
  related_requirement_id: string; content: string; related_analysis_row_id: string | null; ai_reason: string;
  disposition: "pending" | "accepted" | "rejected";
}
export interface ReviewSuggestion {
  id: string; project_id: number; run_id: string; role: string; suggestion_action: "add" | "remove" | "risk";
  module: string; test_item: string; test_basis: string; test_source: string; test_type: string; priority: string;
  related_requirement_id: string; content: string; related_analysis_row_id: string | null; ai_reason: string;
  disposition: "pending" | "accepted" | "rejected";
}
export interface GeneratedCase {
  id: string; project_id: number; run_id: string; generation_id?: string; analysis_row_id: string; title: string;
  objective: string; preconditions: string[]; test_input: string;
  steps: Array<{ order: number; action: string; expected: string }>;
  overall_expectation: string; evidence_requirements: string[]; design_basis: string[]; priority: "P0" | "P1" | "P2" | "P3";
  included: boolean; removed: boolean; mode: RunMode; module?: string; test_item?: string; test_point?: string;
  external_case_number?: string; test_type?: string; attachment?: string; software_version?: string;
}
export interface ExportRecord { id: number; page: string; format: string; filename: string; record_id: string | null; created_at: string; }
export interface WorkspaceState {
  project_id: number; supplemental_notes: string; requirement_version: RequirementVersion | null;
  parse_result?: RequirementPackage | null;
  material_understanding?: MaterialUnderstanding | null;
  template: { mode: "default" | "uploaded"; mapping_id: number | null };
  active_run_ids?: Partial<Record<RunPage, string>>;
  analysis_rows: AnalysisRow[]; suggestions: Suggestion[]; review_suggestions: ReviewSuggestion[];
  analysis_history_rows?: AnalysisRow[];
  cases: GeneratedCase[]; case_generations: CaseGenerationRecord[]; runs: RunEvidence[]; exports: ExportRecord[];
}
export interface CaseTemplateState { mode: "default" | "uploaded"; mapping: TemplateMappingVersion | null; }
