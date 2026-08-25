import { useState } from "react";

import {
  ChangeImpactAnalysis, confirmChangeImpact, confirmRegressionSelection, createChangeImpact,
  createRegressionSelection, RegressionSelection,
} from "./api";

export function ChangeImpactPanel({ projectId }: { projectId: number }) {
  const [baseVersionId, setBaseVersionId] = useState("");
  const [targetVersionId, setTargetVersionId] = useState("");
  const [analysis, setAnalysis] = useState<ChangeImpactAnalysis | null>(null);
  const [selection, setSelection] = useState<RegressionSelection | null>(null);
  const [error, setError] = useState("");

  const analyze = async () => {
    try {
      setAnalysis(await createChangeImpact(projectId, Number(baseVersionId), Number(targetVersionId)));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "变更影响分析失败");
    }
  };

  const confirmChanges = async () => {
    if (!analysis) return;
    setAnalysis(await confirmChangeImpact(projectId, analysis.id, analysis.changes));
  };

  const prepareSelection = async () => {
    if (!analysis) return;
    setSelection(await createRegressionSelection(projectId, analysis.id));
  };

  const confirmSelection = async () => {
    if (selection) setSelection(await confirmRegressionSelection(projectId, selection));
  };

  return <section className="panel" aria-label="V1 到 V2 变更影响和回归治理">
    <h2>V1→V2 变更影响与回归治理</h2>
    <div className="inline-form">
      <label>V1 版本 ID<input value={baseVersionId} onChange={(event) => setBaseVersionId(event.target.value)} /></label>
      <label>
        V2 版本 ID
        <input value={targetVersionId} onChange={(event) => setTargetVersionId(event.target.value)} />
      </label>
      <button onClick={() => void analyze()}>分析需求变更</button>
    </div>
    {error && <p role="alert" className="error">{error}</p>}
    {analysis && <>
      <p role="status">需求变更状态：{analysis.status}；变更 {analysis.changes.length} 项；影响链 {analysis.impacts.length} 项</p>
      <ul>{analysis.changes.map((change) => <li key={change.id}>{change.change_type}：{change.summary}</li>)}</ul>
      {analysis.status === "pending_change_confirmation" && (
        <button onClick={() => void confirmChanges()}>确认需求变更</button>
      )}
      {analysis.status === "confirmed" && <>
        {!selection && <button onClick={() => void prepareSelection()}>生成回归候选</button>}
        {selection && <>
          <p>
            确定性候选 {selection.candidates.filter((candidate) => candidate.deterministic).length} 项，
            AI 补充 {analysis.ai_supplements.length} 项
          </p>
          {selection.status === "pending_confirmation" && (
            <button onClick={() => void confirmSelection()}>确认回归选择</button>
          )}
          {selection.status === "confirmed" && <p role="status">回归选择已由测试工程师确认。</p>}
        </>}
      </>}
    </>}
  </section>;
}
