import { useState } from "react";

import { disposeSuggestion, downloadPageResult, runSuggestions } from "./v020_api";
import type { WorkspaceState } from "./v020_types";
import { PageHeader } from "./UploadWorkspace";
import { WorkflowRunControls } from "./WorkflowRunControls";

export function SuggestionsWorkspace({ projectId, workspace, onChanged }: {
  projectId: number; workspace: WorkspaceState; onChanged: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const latestRun = [...workspace.runs].reverse().find((run) => run.page === "suggestions");
  const dispose = async (id: string, disposition: "accepted" | "rejected") => {
    try { await disposeSuggestion(projectId, id, disposition); await onChanged(); }
    catch (reason) { setError(message(reason)); }
  };
  return <section className="workflow-page">
    <PageHeader title="新增建议" subtitle="由 AI 主动发现遗漏功能、测试项或测试点；接纳后回流需求分析表，默认不勾选。" />
    <WorkflowRunControls projectId={projectId} page="suggestions" actionLabel="AI 分析新增建议" latestRun={latestRun}
      disabled={!workspace.analysis_rows.length} onRun={async (mode, confirmed) => { await runSuggestions(projectId, mode, confirmed); await onChanged(); }} />
    <div className="action-row"><button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "suggestions", "xlsx")}>下载新增建议（Excel）</button>
      <button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "suggestions", "json")}>下载 JSON</button></div>
    <section className="card-list" aria-label="新增建议结果">
      {!workspace.suggestions.length && <p className="empty-hint">尚未执行新增建议分析；此步骤可选，不阻塞测试用例生成。</p>}
      {[...workspace.suggestions].reverse().map((item) => <article className="suggestion-card" key={item.id}>
        <header><strong>{typeLabel(item.suggestion_type)} · {priorityLabel(item.priority)}</strong><span className={`status-pill ${item.disposition}`}>{dispositionLabel(item.disposition)}</span></header>
        <h3>{item.content}</h3><p>关联需求点：{item.related_analysis_row_id ?? "整体范围"}</p><p>AI 理由：{item.ai_reason}</p>
        {item.disposition === "pending" && <div className="action-row"><button type="button" onClick={() => void dispose(item.id, "accepted")}>接纳并回流</button>
          <button type="button" className="secondary" onClick={() => void dispose(item.id, "rejected")}>拒绝</button></div>}
      </article>)}
    </section>
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

const typeLabel = (value: string) => ({ function: "遗漏功能", test_item: "新增测试项", test_point: "新增测试点" })[value] ?? value;
const priorityLabel = (value: string) => ({ high: "高优先级", medium: "中优先级", low: "低优先级" })[value] ?? value;
const dispositionLabel = (value: string) => ({ pending: "待处置", accepted: "已接纳", rejected: "已拒绝" })[value] ?? value;
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
