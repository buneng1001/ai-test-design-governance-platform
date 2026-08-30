// 执行批次与执行结果领域请求。
import { request, downloadResponseFile } from "./api_client";
import type { ExecutionBatch, ExecutionBatchResults, ExecutionResultStatus, TestTask } from "./api_types";

export const createExecutionBatch = (projectId: number, taskId: string,
  input: {
    product_version: string;
    requirement_version_id: number;
    environment: string;
    scope: string;
    responsible_person: string;
    stable_case_ids: string[];
  }): Promise<ExecutionBatch> => request(
  `/api/projects/${projectId}/test-tasks/${taskId}/execution-batches`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) },
);
export const downloadManualExecutionFile = async (projectId: number, batchId: number): Promise<void> => {
  const response = await fetch(`/api/projects/${projectId}/execution-batches/${batchId}/manual-file`);
  await downloadResponseFile(response, `execution-batch-${batchId}.csv`);
};
export const importExecutionResults = (projectId: number, batchId: number,
  sourceType: "manual" | "test_execution_diagnostics" | "generic_automation", results: Array<Record<string,
    unknown>>): Promise<ExecutionBatchResults> => request(
  `/api/projects/${projectId}/execution-batches/${batchId}/results/import`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_type: sourceType, results }) },
);
export const resolveExecutionConflict = async (projectId: number, batchId: number, conflictId: number,
  decision: ExecutionResultStatus, rationale: string,
    confirmerName: string): Promise<ExecutionBatchResults["conflicts"][number]> => {
  await request<ExecutionBatchResults["conflicts"][number]>(
    `/api/projects/${projectId}/execution-batches/${batchId}/conflicts/${conflictId}/resolve`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, rationale,
      confirmer_name: confirmerName }),
  });
  const summary = await getExecutionResults(projectId, batchId);
  const conflict = summary.conflicts.find((item) => item.id === conflictId);
  if (!conflict) throw new Error("结果冲突不存在");
  return conflict;
};
export const getExecutionResults = (projectId: number, batchId: number): Promise<ExecutionBatchResults> => request(
  `/api/projects/${projectId}/execution-batches/${batchId}/results`,
);
export const confirmExecutionConclusion = (projectId: number, batchId: number, conclusion: ExecutionResultStatus,
  rationale: string, confirmerName: string): Promise<ExecutionBatchResults> => request(
  `/api/projects/${projectId}/execution-batches/${batchId}/conclusion`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ conclusion, rationale,
      confirmer_name: confirmerName }) },
);
