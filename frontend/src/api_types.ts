// 前端 API 使用的领域数据类型，集中维护以保持请求函数文件职责单一。

export interface AssetProvenanceInput {
  name: string;
  media_type?: string;
  asset_type:
    | "requirement_material"
    | "case_template"
    | "mock_output"
    | "evaluation_truth"
    | "result_input"
    | "other";
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
  size_bytes: number;
  created_at: string;
  boundary: "original_synthetic" | "public_authorized" | "prohibited" | "unknown";
  can_enter_requirement_package: boolean;
  can_enter_model_context: boolean;
  reason: string;
  media_type: string;
}

export interface RequirementFileInput {
  asset_id: number;
  filename: string;
  media_type: string;
  content_base64: string;
}

export interface ParseDiagnostic {
  asset_id: number;
  filename: string;
  code: string;
  severity: "warning" | "error";
  message: string;
}

export interface RequirementMaterial {
  asset_id: number;
  asset_revision: number;
  filename: string;
  media_type: string;
  format: "markdown" | "text" | "json" | "yaml" | "openapi" | "docx" | "pdf" | "png" | "jpg" | "unsupported";
  sha256: string;
  content_base64: string;
  parse_status: "complete" | "partial" | "failed" | "rejected";
  fragments: Array<{
    text: string;
    source_reference: { reference_id: string; asset_id: number; filename: string; locator: string };
  }>;
  visual_inferences: Array<{
    status: "pending_confirmation";
    description: string;
    source_reference: { reference_id: string; asset_id: number; filename: string; locator: string };
  }>;
  diagnostics: ParseDiagnostic[];
}

export interface RequirementPackage {
  id: number;
  project_id: number;
  name: string;
  status: "draft" | "published";
  materials: RequirementMaterial[];
  diagnostics: ParseDiagnostic[];
  created_at: string;
  published_version_id: number | null;
}

export interface RequirementVersion {
  id: number;
  project_id: number;
  package_id: number;
  version: number;
  name: string;
  materials: RequirementMaterial[];
  diagnostics: ParseDiagnostic[];
  created_at: string;
}

export interface RequirementAnalysis {
  id: number;
  requirement_version_id: number;
  status: "draft" | "confirmed";
  is_mock: boolean;
  requirements: Array<{
    requirement_id: string;
    name: string;
    statement: string;
    requirement_type: string;
    module: string;
    source_references: Array<{ filename: string; locator: string; reference_id: string }>;
    analysis_note: string;
  }>;
  selected_requirement_ids: string[];
  conflicts: Array<{
    conflict_id: string; topic: string; srs_text: string;
    srs_source: { filename: string; locator: string; reference_id: string };
    implementation_text: string;
    implementation_source: { filename: string; locator: string; reference_id: string };
    affected_modules: string[]; affected_test_items: string[];
    decision: "unresolved" | "srs_preferred" | "implementation_preferred" | "both_retained" | "awaiting_external_confirmation";
    decided_by: string | null; decision_note: string | null;
  }>;
  test_items: Array<{ test_item_id: string; name: string; module: string; requirement_ids: string[] }>;
  acceptance_criteria: Array<{ criterion_id: string; statement: string; requirement_id: string }>;
  atomic_requirements: Array<{
    candidate_id: string;
    stable_requirement_id: string | null;
    statement: string;
    source_reference: { locator: string; filename: string };
    decision: "pending_confirmation" | "accepted" | "rejected";
  }>;
  findings: Array<{
    finding_id: string;
    finding_type: string;
    summary: string;
    reason: string;
    status: string;
    source_reference: { locator: string; filename: string; reference_id?: string } | null;
  }>;
  visual_inferences: Array<{
    inference_id: string;
    description: string;
    source_reference: { locator: string; filename: string };
    decision: "pending_confirmation" | "accepted" | "rejected";
  }>;
  confirmed_by: string | null;
}

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

export interface TestDesign {
  id: number;
  requirement_version_id: number;
  status: "draft" | "confirmed";
  dimensions: Array<{ id: string; name: string; status: "active" | "inactive" }>;
  scope_items: Array<{ id: string; title: string; primary_dimension_id: string }>;
  risks: Array<{
    scope_item_id: string;
    final_score: number;
    risk_level: string;
    priority: string;
    factors: Array<{ key: string; name: string; score: number; weight: number; source_references: unknown[] }>;
  }>;
  automation_candidates: Array<{
    scope_item_id: string;
    suggested_score: number;
    decision: string;
    suggestion_reason: string;
    factors: {
      regression_value: number;
      determinism: number;
      environment_control: number;
      saving_benefit: number;
      maintenance_cost: number;
      manual_observation: number;
    };
  }>;
  confirmed_by: string | null;
}

export interface TemplateColumn {
  index: number;
  name: string;
  sample_values: string[];
}

export interface TemplateSheet {
  name: string;
  index: number;
  role_suggestion: "case" | "instruction" | "dictionary" | "statistics" | "unknown";
  role: "case" | "instruction" | "dictionary" | "statistics" | "unknown";
  title_row_candidates: number[];
  title_row: number | null;
  columns: TemplateColumn[];
  participates: boolean;
  field_mapping: Record<string, string>;
  diagnostics: Array<{ code: string; severity: "warning" | "error"; message: string }>;
}

export interface TemplateMappingVersion {
  id: number;
  project_id: number;
  version: number;
  filename: string;
  format: "xlsx" | "csv";
  status: "draft" | "confirmed";
  sheets: TemplateSheet[];
  diagnostics: Array<{ code: string; severity: "warning" | "error"; message: string }>;
  retained_sheet_names: string[];
  confirmed_by: string | null;
}

export interface CandidateTestCase {
  id: string;
  title: string;
  objective: string;
  variant: string;
  preconditions: string[];
  steps: Array<{ order: number; action: string; input: string; expected: string }>;
  overall_expectation: string;
  evidence_requirements: string[];
  requirement_ids: string[];
  requirement_references: unknown[];
  scope_item_id: string;
  risk_item_id: string;
  priority: string;
  case_sheet_name: string;
  automation_mapping: string | null;
  unexpressed_fields: string[];
  design_basis: Array<{ method: string; reason: string }>;
  input?: string;
  test_type?: string;
  module?: string;
  test_item?: string;
  pre_test_notes?: string;
  software_version?: string;
}

export interface CaseGeneration {
  id: number;
  ai_run_id: number;
  ai_run_status: string;
  is_mock: boolean;
  status: "succeeded" | "empty" | "validation_failed" | "failed" | "needs_confirmation";
  template_diagnostics: Array<{ code: string; message: string }>;
  candidates: CandidateTestCase[];
}

export interface CaseReviewSuggestion {
  id: string;
  candidate_id: string;
  role: "product_manager" | "test_manager" | "project_manager";
  suggestion_type: string;
  summary: string;
  rationale: string;
  source_references: unknown[];
  limitations: string[];
  disposition: "accepted" | "rejected" | "modified" | null;
}

export interface CaseReviewBatch {
  id: number;
  generation_id: number;
  status: "in_progress" | "completed" | "confirmed";
  reviewer_runs: Array<{ role: string; ai_run_id: number }>;
  suggestions: CaseReviewSuggestion[];
  groups: Array<{ id: string; summary: string; original_suggestion_ids: string[]; source_roles: string[] }>;
  revisions: Array<{
    id: string;
    candidate_id: string;
    revision: number;
    stable_case_id: string | null;
    lifecycle_status: "draft" | "effective" | "closed" | "deprecated" | "superseded";
    participation_status: "included" | "not_included" | "pending_impact" | "pending_retest";
    candidate?: CandidateTestCase;
    original_candidate?: CandidateTestCase | null;
    manual_modified?: boolean;
    edit_history?: Array<{ reason: string; title: string }>;
  }>;
  inclusion: Record<string, boolean>;
  confirmed_by: string | null;
}

export interface TestTask {
  contract_version: "test-task.v1";
  task_id: string;
  task_version: number;
  project_id: number;
  case_review_batch_id: number;
  execution_scope: "selected";
  execution_target:
    | "manual" | "test_execution_diagnostics" | "generic_automation" | "external_executor" | "unspecified";
  cases: Array<{
    stable_case_id: string;
    case_revision_id: string;
    case_revision: number;
    external_case_number?: string | null;
    title: string;
    priority: "P0" | "P1" | "P2" | "P3";
    preconditions: string[];
    parameters: Record<string, string>;
    steps: Array<Record<string, string | number>>;
    expected_result: string;
    verdict_method: "expected_result_match" | "manual_observation" | "adapter_defined";
    evidence_requirements: string[];
  }>;
  published_by: string;
  published_at: string;
}

export interface ExecutionBatch {
  id: number;
  project_id: number;
  test_task_id: string;
  test_task_version: number;
  product_version: string;
  requirement_version_id: number;
  environment: string;
  scope: string;
  responsible_person: string;
  execution_target: string;
  cases: Array<{
    stable_case_id: string;
    case_revision_id: string;
    case_revision: number;
    external_case_number: string | null;
    lifecycle_status: "effective" | "closed" | "deprecated" | "superseded";
    participation_status: "included" | "not_included" | "pending_impact" | "pending_retest";
    execution_sequence: number;
    display_number: string;
    title: string;
  }>;
  manual_file_format: "csv";
  created_at: string;
}

export type ExecutionResultStatus =
  | "passed" | "execution_failed" | "blocked" | "not_executed" | "execution_error";

export interface ExecutionResultRecord {
  id: number;
  batch_id: number;
  source_type: "manual" | "test_execution_diagnostics" | "generic_automation";
  source_record_id: string;
  stable_case_id: string | null;
  case_revision_id: string | null;
  execution_sequence: number | null;
  status: ExecutionResultStatus;
  actual_result: string;
  reason: string;
  executor: string;
  evidence_references: string[];
  match_status: "matched" | "unresolved" | "rejected";
  retest_of_result_id: number | null;
}

export interface ExecutionBatchResults {
  batch_id: number;
  records: ExecutionResultRecord[];
  unresolved_records: ExecutionResultRecord[];
  conflicts: Array<{
    id: number;
    result_ids: number[];
    statuses: Record<string, ExecutionResultStatus>;
    status: "open" | "resolved";
    decision: ExecutionResultStatus | null;
    rationale: string | null;
    confirmed_by: string | null;
  }>;
  case_summaries: Array<{
    stable_case_id: string;
    initial_result: ExecutionResultRecord | null;
    latest_result: ExecutionResultRecord | null;
    history: ExecutionResultRecord[];
  }>;
  conclusion: { conclusion: ExecutionResultStatus; rationale: string; confirmer_name: string } | null;
}

export interface CoverageMetric {
  label: string;
  numerator: number;
  denominator: number;
  percentage: number;
  covered_items: string[];
  uncovered_items: string[];
  high_risk_gaps: string[];
  quality_issues: Array<{ id: number; phenomenon: string; severity: string }>;
  execution_evidence: Array<{ id: number; stable_case_id: string | null; evidence_references: string[] }>;
}

export interface CoverageSummary {
  metrics: Record<string, CoverageMetric>;
}

export interface ChangeImpactAnalysis {
  id: number;
  base_version_id: number;
  target_version_id: number;
  status: "pending_change_confirmation" | "confirmed";
  changes: Array<{
    id: string;
    change_type: string;
    summary: string;
    base_source_reference: unknown | null;
    target_source_reference: unknown | null;
    status: "pending_confirmation" | "confirmed" | "rejected";
  }>;
  impacts: Array<{ kind: string; identifier: string; title: string; reason: string }>;
  regression_candidates: RegressionCandidate[];
  ai_supplements: RegressionCandidate[];
}

export interface RegressionCandidate {
  stable_case_id: string;
  title: string;
  deterministic: boolean;
  reasons: string[];
  ai_supplement_reason: string | null;
  selected: boolean | null;
  decision_reason: string | null;
}

export interface RegressionSelection {
  id: number;
  analysis_id: number;
  status: "pending_confirmation" | "confirmed";
  candidates: RegressionCandidate[];
}

export interface ReportDocument {
  contract_version: string;
  report_type: "test_design" | "execution_governance" | "audit_package";
  project_id: number;
  generated_at: string;
  summary: Record<string, unknown>;
  metrics: Record<string, unknown>;
  evidence: Record<string, unknown>;
}


