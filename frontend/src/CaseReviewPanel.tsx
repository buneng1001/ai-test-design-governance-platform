import { useState } from "react";

import {
  CaseReviewBatch, CaseReviewSuggestion, confirmCaseReviews, createCaseReviews, disposeCaseReviewSuggestion,
} from "./api";

const roleLabels: Record<string, string> = {
  product_manager: "产品经理评审员",
  test_manager: "测试经理评审员",
  project_manager: "项目经理评审员",
};

export function CaseReviewPanel({ projectId, generationId, candidateIds }: {
  projectId: number;
  generationId: number;
  candidateIds: string[];
}) {
  const [batch, setBatch] = useState<CaseReviewBatch | null>(null);
  const [error, setError] = useState("");

  const startReview = async () => {
    try {
      setBatch(await createCaseReviews(projectId, generationId));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "三角色 AI 评审启动失败");
    }
  };

  const dispose = async (suggestion: CaseReviewSuggestion, decision: "accepted" | "rejected") => {
    if (!batch) return;
    try {
      setBatch(await disposeCaseReviewSuggestion(projectId, batch.id, suggestion.id, decision));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI 评审建议处置失败");
    }
  };

  const confirm = async () => {
    if (!batch) return;
    try {
      setBatch(await confirmCaseReviews(projectId, batch.id, candidateIds, "测试工程师"));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "用例确认失败");
    }
  };

  return <section className="panel" aria-label="三角色 AI 评审与用例确认">
    <h2>三角色 AI 评审与用例确认</h2>
    {!batch && <button onClick={() => void startReview()}>开始三角色 AI 评审</button>}
    {error && <p role="alert" className="error">{error}</p>}
    {batch && <>
      <p role="status">评审批次：{batch.status}；独立 AI 运行：{batch.reviewer_runs.length} 个；Mock AI 运行</p>
      {batch.groups.map((group) => <article key={group.id} className="case-card">
        <h3>{group.summary}</h3>
        <p>归并来源：{group.source_roles.map((role) => roleLabels[role] ?? role).join("、")}</p>
        <p>原始建议：{group.original_suggestion_ids.length} 条，仍保留角色来源</p>
      </article>)}
      {batch.suggestions.map((suggestion) => <article key={suggestion.id} className="case-card">
        <p>{roleLabels[suggestion.role]}：{suggestion.summary}</p>
        <p>{suggestion.rationale}</p>
        <p>限制：{suggestion.limitations.join("；")}</p>
        {!suggestion.disposition && <>
          <button onClick={() => void dispose(suggestion, "accepted")}>采纳</button>
          <button onClick={() => void dispose(suggestion, "rejected")}>拒绝</button>
        </>}
        {suggestion.disposition && <p>处置：{suggestion.disposition}</p>}
      </article>)}
      <button disabled={batch.suggestions.some((item) => !item.disposition)} onClick={() => void confirm()}>
        完成用例确认
      </button>
      {batch.status === "confirmed" && <p role="status">用例已确认，已记录确认人和用例纳入决定。</p>}
    </>}
  </section>;
}
