// API 公共兼容门面，保持组件原有的统一导入方式。
export type { ProjectSettings, ProjectInput, Project } from "./api_types_project";
export type { ConnectionTestResult, ModelDiscoveryResult, ModelOption, ModelProviderId, ModelProviderOption,
  ModelServiceError, SessionModelConfig, SessionModelConfigStatus, AIRun, AIRunControl } from "./api_types_ai";
export { isAIRunControl } from "./api_types_ai";
export type {
  AssetProvenanceInput, AssetProvenanceRecord, RequirementFileInput, ParseDiagnostic, RequirementMaterial,
  RequirementPackage, RequirementVersion, RequirementAnalysis, TestPointReview, TestDesign, TemplateColumn, TemplateSheet,
  TemplateMappingVersion, CandidateTestCase, CaseGeneration, CaseQualityReport, StandardCasePreview, CaseReviewSuggestion, CaseReviewBatch, TestTask,
  ExecutionBatch, ExecutionResultStatus, ExecutionResultRecord, ExecutionBatchResults, CoverageMetric,
  CoverageSummary, ChangeImpactAnalysis, RegressionCandidate, RegressionSelection, ReportDocument,
  ProjectWorkflowView,
} from "./api_types";

export {
  listProjects, getProject, createProject, updateProject, deleteProject,
} from "./project_api";
export {
  listAssets, createAsset, deleteAsset,
} from "./asset_api";
export {
  createRequirementPackage, reparseRequirementPackage, publishRequirementPackage, listRequirementVersions, createRequirementReview, getRequirementReview,
  startRequirementReviewRun, advanceRequirementReviewRun, resumeRequirementReviewRun,
  updateAtomicRequirement, bulkConfirmAtomicRequirements, updateFinding, updateVisualInference, confirmRequirementReview,
  updateRequirementSelection, decideRequirementConflict, generateReviewSuggestions, disposeReviewSuggestion,
  confirmSupplementalRequirements, generateTestPointReview, updateTestPointScope, confirmTestPointReview,
} from "./requirement_api";
export {
  listModelProviders, getSessionModelConfig, saveSessionModelConfig, discoverSessionModels,
  testSessionModelConfig, clearSessionModelConfig, listAIRuns, getAIRunControl, stopAIRunControl,
} from "./ai_api";
export {
  createTestDesign, confirmTestDesign, addTestDimension, adjustTestRisk, decideAutomation,
} from "./design_api";
export { uploadTemplate, confirmTemplate, validateTemplate } from "./template_api";
export {
  generateCases, startCaseGenerationRun, advanceCaseGenerationRun, resumeCaseGenerationRun, getCaseGeneration,
  getGeneratedCasePreview, getGeneratedCaseQualityReport, exportGeneratedCaseFile, createCaseReviews, disposeCaseReviewSuggestion, confirmCaseReviews, changeCaseStatus,
  editCase, editGeneratedCase, setGeneratedCaseRemoved, changeCaseStatuses, exportCaseFile, getCaseQualityReport,
  getStandardCasePreview, exportStandardCaseFile, publishTestTask,
} from "./case_api";
export {
  createExecutionBatch, downloadManualExecutionFile, importExecutionResults, resolveExecutionConflict,
  getExecutionResults, confirmExecutionConclusion,
} from "./execution_api";
export {
  getCoverage, createChangeImpact, confirmChangeImpact, createRegressionSelection,
  confirmRegressionSelection, getAuditPackage,
} from "./governance_api";
export { getProjectWorkflow } from "./workflow_api";
