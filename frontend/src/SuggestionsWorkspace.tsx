import { useState } from "react";

import { disposeSuggestion, downloadPageResult, runSuggestions } from "./v020_api";
import type { WorkspaceState } from "./v020_types";
import { visibleRunForPage } from "./v020_run_state";
import { PageHeader } from "./UploadWorkspace";
import { RequirementPointTable } from "./RequirementPointTable";
import { WorkflowRunControls } from "./WorkflowRunControls";

export function SuggestionsWorkspace({ projectId, workspace, onChanged }: {
  projectId: number; workspace: WorkspaceState; onChanged: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const latestRun = visibleRunForPage(workspace, "suggestions");
  const dispose = async (id: string, disposition: "accepted" | "rejected") => {
    try { await disposeSuggestion(projectId, id, disposition); await onChanged(); }
    catch (reason) { setError(message(reason)); }
  };
  return <section className="workflow-page">
    <PageHeader title="新增建议" subtitle="由 AI 主动发现遗漏测试项、移除建议或风险项；接纳后回流需求分析表，默认不勾选。" />
    <WorkflowRunControls projectId={projectId} page="suggestions" actionLabel="AI 分析新增建议" latestRun={latestRun}
      onRunSettled={onChanged}
      disabled={!workspace.analysis_rows.length} onRun={async (mode, confirmed) => {
        return runSuggestions(projectId, mode, confirmed);
      }} />
    <div className="action-row"><button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "suggestions", "xlsx")}>下载新增建议（Excel）</button>
      <button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "suggestions", "json")}>下载 JSON</button></div>
    <section aria-label="新增建议结果">
      {!workspace.suggestions.length && <p className="empty-hint">尚未执行新增建议分析；此步骤可选，不阻塞测试用例生成。</p>}
      <RequirementPointTable rows={[...workspace.suggestions].reverse().map((item, index) => ({
        ...item, total_index: index + 1,
        action: <div className="table-actions"><span className={`status-pill ${item.disposition}`}>
          {actionLabel(item.suggestion_action)} · {dispositionLabel(item.disposition)}</span>
          {item.disposition === "pending" && <><button type="button" className="text-button" onClick={() => void dispose(item.id, "accepted")}>接纳并回流</button>
            <button type="button" className="text-button" onClick={() => void dispose(item.id, "rejected")}>拒绝</button></>}</div>,
      }))} />
    </section>
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

const actionLabel = (value: string) => ({ add: "建议增加", remove: "建议减少", risk: "风险项" })[value] ?? value;
const dispositionLabel = (value: string) => ({ pending: "待处置", accepted: "已接纳", rejected: "已拒绝" })[value] ?? value;
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
