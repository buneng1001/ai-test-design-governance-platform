import { useEffect, useState } from "react";

import {
  confirmSupplementalRequirements, disposeReviewSuggestion, generateReviewSuggestions, getRequirementReview,
  RequirementAnalysis,
} from "./api";

export function ReviewSuggestionsPanel({ projectId, analysisId, onWorkflowChanged }: {
  projectId: number;
  analysisId: number | null;
  onWorkflowChanged: () => void;
}) {
  const [analysis, setAnalysis] = useState<RequirementAnalysis | null>(null);
  const [error, setError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [confirmerName, setConfirmerName] = useState("测试工程师");

  useEffect(() => {
    if (!analysisId) return;
    void getRequirementReview(projectId, analysisId).then(setAnalysis).catch((reason: unknown) => setError(message(reason)));
  }, [projectId, analysisId]);

  const update = (request: Promise<RequirementAnalysis>) => {
    void request.then((result) => {
      setAnalysis(result);
      setError("");
      onWorkflowChanged();
    }).catch((reason: unknown) => setError(message(reason)));
  };

  if (!analysisId) return <p className="muted">请先在结构预览页确认需求。</p>;
  if (!analysis) return error ? <p role="alert" className="error">{error}</p> : <p className="muted">正在恢复新增建议…</p>;
  return <section aria-labelledby="review-suggestions">
    <h3 id="review-suggestions">Step 03–06 新增建议</h3>
    {!analysis.suggestions.length && <button onClick={() => update(generateReviewSuggestions(projectId, analysis.id))}>生成新增建议</button>}
    <p className="field-help">建议只基于已确认并选择的需求生成。采纳补充需求不会直接写入基线，必须再次确认后才获得稳定需求 ID。</p>
    {analysis.suggestions.map((item) => <article className="suggestion-card" key={item.suggestion_id}>
      <h4>{directionLabel(item.direction)} · {item.problem_type}</h4>
      <p>{item.statement}</p>
      <p>来源类型：{sourceLabel(item.source_type)}；影响范围：{item.impact_scope}</p>
      <p>关联需求：{item.related_requirement_ids.join("、")}；来源依据：{item.source_references.map((source) => `${source.filename} ${source.locator}`).join("；")}</p>
      <p>处置：{dispositionLabel(item.disposition)}</p>
      {item.disposition === "pending_confirmation" && <div className="button-group">
        <button onClick={() => update(disposeReviewSuggestion(projectId, analysis.id, item.suggestion_id, "accepted"))}>采纳</button>
        <button onClick={() => update(disposeReviewSuggestion(projectId, analysis.id, item.suggestion_id, "rejected"))}>拒绝</button>
        <button onClick={() => update(disposeReviewSuggestion(projectId, analysis.id, item.suggestion_id, "awaiting_external_confirmation"))}>待外部确认</button>
        <label>修改建议<input aria-label={`修改 ${item.suggestion_id}`} value={drafts[item.suggestion_id] ?? item.statement}
          onChange={(event) => setDrafts({ ...drafts, [item.suggestion_id]: event.target.value })} /></label>
        <button onClick={() => update(disposeReviewSuggestion(
          projectId, analysis.id, item.suggestion_id, "modified", drafts[item.suggestion_id] ?? item.statement,
        ))}>保存修改</button>
      </div>}
    </article>)}
    {analysis.supplemental_requirement_candidates.length > 0 && <section>
      <h3>待重新确认的补充需求</h3>
      {analysis.supplemental_requirement_candidates.map((item) => <p key={item.candidate_id}>{item.statement} ·
        {item.decision === "confirmed" ? `稳定需求 ID：${item.stable_requirement_id}` : "等待需求确认"}</p>)}
      {analysis.supplemental_requirement_candidates.some((item) => item.decision === "pending_confirmation") && <>
        <label>确认人名称<input value={confirmerName} onChange={(event) => setConfirmerName(event.target.value)} /></label>
        <button onClick={() => update(confirmSupplementalRequirements(projectId, analysis.id,
          analysis.supplemental_requirement_candidates.filter((item) => item.decision === "pending_confirmation").map((item) => item.candidate_id), confirmerName,
        ))}>确认补充需求</button>
      </>}
    </section>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
const directionLabel = (value: string): string => ({ normal: "正常场景", exception: "异常场景", boundary: "边界条件", risk: "隐性风险" })[value] ?? value;
const sourceLabel = (value: string): string => ({ material_explicit: "材料明示", human_confirmed: "人工确认", analysis_inference: "分析推导", awaiting_confirmation: "待确认" })[value] ?? value;
const dispositionLabel = (value: string): string => ({ pending_confirmation: "待处置", accepted: "已采纳", rejected: "已拒绝", modified: "已修改", awaiting_external_confirmation: "待外部确认" })[value] ?? value;
