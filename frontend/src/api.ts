// API 公共兼容门面，保持组件原有的统一导入方式。
export type { ProjectSettings, ProjectInput, Project } from "./api_types_project";
export type { ModelProviderId, ModelProviderOption, SessionModelConfig, SessionModelConfigStatus,
  AIRun } from "./api_types_ai";
export type {
  AssetProvenanceInput, AssetProvenanceRecord, RequirementFileInput, ParseDiagnostic, RequirementMaterial,
  RequirementPackage, RequirementVersion, RequirementAnalysis, TestDesign, TemplateColumn, TemplateSheet,
  TemplateMappingVersion, CandidateTestCase, CaseGeneration, CaseReviewSuggestion, CaseReviewBatch, TestTask,
  ExecutionBatch, ExecutionResultStatus, ExecutionResultRecord, ExecutionBatchResults, CoverageMetric,
  CoverageSummary, ChangeImpactAnalysis, RegressionCandidate, RegressionSelection, ReportDocument,
} from "./api_types";

export {
  listProjects, getProject, createProject, updateProject,
} from "./project_api";
export {
  listAssets, createAsset,
} from "./asset_api";
export {
  createRequirementPackage, publishRequirementPackage, listRequirementVersions, createRequirementReview,
  updateAtomicRequirement, updateFinding, updateVisualInference, confirmRequirementReview,
  updateRequirementSelection, decideRequirementConflict,
} from "./requirement_api";
export {
  readStoredSessionModelConfig, listModelProviders, getSessionModelConfig, saveSessionModelConfig,
  testSessionModelConfig, clearSessionModelConfig, listAIRuns,
} from "./ai_api";
export {
  createTestDesign, confirmTestDesign, addTestDimension, adjustTestRisk, decideAutomation,
} from "./design_api";
export { uploadTemplate, confirmTemplate, validateTemplate } from "./template_api";
export {
  generateCases, createCaseReviews, disposeCaseReviewSuggestion, confirmCaseReviews, changeCaseStatus,
  editCase, changeCaseStatuses, exportCaseFile, publishTestTask,
} from "./case_api";
export {
  createExecutionBatch, downloadManualExecutionFile, importExecutionResults, resolveExecutionConflict,
  getExecutionResults, confirmExecutionConclusion,
} from "./execution_api";
export {
  getCoverage, createChangeImpact, confirmChangeImpact, createRegressionSelection,
  confirmRegressionSelection, getAuditPackage,
} from "./governance_api";
