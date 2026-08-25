import { FormEvent, useState } from "react";

import {
  confirmExecutionConclusion,
  ExecutionBatchResults,
  ExecutionResultStatus,
  getExecutionResults,
  importExecutionResults,
  resolveExecutionConflict,
} from "./api";

interface Props {
  projectId: number;
}

const statuses: Array<[ExecutionResultStatus, string]> = [
  ["passed", "通过"], ["execution_failed", "执行失败"], ["blocked", "阻塞"],
  ["not_executed", "未执行"], ["execution_error", "执行异常"],
];

export function ExecutionResultPanel({ projectId }: Props) {
  const [batchId, setBatchId] = useState("");
  const [sourceType, setSourceType] = useState<
    "manual" | "test_execution_diagnostics" | "generic_automation"
  >("manual");
  const [payload, setPayload] = useState('[{"source_record_id":"record-1","stable_case_id":"case-1",'
    + '"case_revision_id":"revision-1","status":"passed"}]');
  const [summary, setSummary] = useState<ExecutionBatchResults | null>(null);
  const [error, setError] = useState("");

  const importResults = async (event: FormEvent) => {
    event.preventDefault();
    try {
      setError("");
      setSummary(await importExecutionResults(projectId, Number(batchId), sourceType, JSON.parse(payload)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "结果导入失败");
    }
  };

  const resolve = async (conflictId: number) => {
    try {
      await resolveExecutionConflict(
        projectId, Number(batchId), conflictId, "passed", "测试工程师比较证据后确认通过", "测试工程师",
      );
      setSummary(await getExecutionResults(projectId, Number(batchId)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "冲突处理失败");
    }
  };

  const confirm = async () => {
    try {
      setSummary(await confirmExecutionConclusion(
        projectId, Number(batchId), "passed", "测试工程师确认本批次结论", "测试工程师",
      ));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批次结论确认失败");
    }
  };

  return <section className="panel">
    <h2>导入运行结果</h2>
    <p className="muted">保留每次结果事实；未匹配结果和结果冲突必须由测试工程师处理。</p>
    <form className="project-form" onSubmit={importResults}>
      <label>执行批次 ID<input value={batchId} onChange={(event) => setBatchId(event.target.value)} required /></label>
      <label>结果来源<select value={sourceType} onChange={(event) => setSourceType(
        event.target.value as "manual" | "test_execution_diagnostics" | "generic_automation",
      )}>
        <option value="manual">人工结果</option>
        <option value="test_execution_diagnostics">测试执行与诊断平台</option>
        <option value="generic_automation">通用自动化</option>
      </select></label>
      <label>结果 JSON<textarea value={payload} onChange={(event) => setPayload(event.target.value)} required /></label>
      <button type="submit">导入结果</button>
    </form>
    {error && <p role="alert" className="error">{error}</p>}
    {summary && <div role="status">
      <p>已导入 {summary.records.length} 条结果，未匹配 {summary.unresolved_records.length} 条。</p>
      {summary.conflicts.filter((conflict) => conflict.status === "open").map((conflict) => (
        <p key={conflict.id}>结果冲突 #{conflict.id} <button type="button" onClick={() => void resolve(conflict.id)}>
          记录决定并解决
        </button></p>
      ))}
      <label>批次结论
        <select aria-label="批次结论" defaultValue="passed">
          {statuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <button type="button" onClick={() => void confirm()}>确认批次结论</button>
      {summary.conclusion && <p>批次结论已确认：{summary.conclusion.conclusion}</p>}
    </div>}
  </section>;
}
