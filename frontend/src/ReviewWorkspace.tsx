import { useState } from "react";

import { disposeReviewSuggestion, downloadPageResult, runReview, skipReview } from "./v020_api";
import type { WorkspaceState } from "./v020_types";
import { PageHeader } from "./UploadWorkspace";
import { WorkflowRunControls } from "./WorkflowRunControls";

const roleLabels = { product_manager: "产品经理", project_manager: "项目经理", test_manager: "测试经理" };

export function ReviewWorkspace({ projectId, workspace, onChanged, onSkip }: {
  projectId: number; workspace: WorkspaceState; onChanged: () => Promise<void>; onSkip: () => void;
}) {
  const [roles, setRoles] = useState<string[]>(["test_manager"]);
  const [error, setError] = useState("");
  const latestRun = [...workspace.runs].reverse().find((run) => run.page === "review");
  const toggleRole = (role: string, checked: boolean) => setRoles(checked ? [...new Set([...roles, role])] : roles.filter((item) => item !== role));
  const dispose = async (id: string, disposition: "accepted" | "rejected") => {
    try { await disposeReviewSuggestion(projectId, id, disposition); await onChanged(); }
    catch (reason) { setError(message(reason)); }
  };
  const skip = async () => { try { await skipReview(projectId); onSkip(); } catch (reason) { setError(message(reason)); } };
  return <section className="workflow-page">
    <PageHeader title="审核" subtitle="可选的 AI 角色审核；审核建议由你决定是否接纳，不具有审批权。" badge="可跳过" />
    <fieldset className="role-picker"><legend>选择审核身份</legend>{Object.entries(roleLabels).map(([role, label]) => <label key={role}>
      <input type="checkbox" checked={roles.includes(role)} onChange={(event) => toggleRole(role, event.target.checked)} /> {label}</label>)}</fieldset>
    <WorkflowRunControls projectId={projectId} page="review" roles={roles} actionLabel="开始审核" latestRun={latestRun}
      disabled={!workspace.analysis_rows.length || !roles.length}
      onRun={async (mode, confirmed) => { await runReview(projectId, mode, confirmed, roles); await onChanged(); }} />
    <div className="action-row"><button type="button" className="secondary" onClick={() => void skip()}>跳过审核，进入测试用例</button>
      <button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "review", "json")}>下载审核报告</button></div>
    <section className="card-list" aria-label="审核建议结果">
      {!workspace.review_suggestions.length && <p className="empty-hint">尚未执行审核；可以直接跳过。</p>}
      {[...workspace.review_suggestions].reverse().map((item) => <article className="suggestion-card" key={item.id}>
        <header><strong>{roleLabels[item.role as keyof typeof roleLabels] ?? item.role} · {findingLabel(item.finding_type)}</strong>
          <span className={`status-pill ${item.disposition}`}>{dispositionLabel(item.disposition)}</span></header>
        <h3>{item.content}</h3><p>关联需求点：{item.related_analysis_row_id ?? "整体范围"}</p><p>AI 理由：{item.ai_reason}</p>
        {item.disposition === "pending" && <div className="action-row"><button type="button" onClick={() => void dispose(item.id, "accepted")}>接纳并回流</button>
          <button type="button" className="secondary" onClick={() => void dispose(item.id, "rejected")}>不接纳</button></div>}
      </article>)}
    </section>
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

const findingLabel = (value: string) => ({ risk: "风险", omission: "遗漏", conflict: "冲突", change: "修改建议" })[value] ?? value;
const dispositionLabel = (value: string) => ({ pending: "待处置", accepted: "已接纳", rejected: "不接纳" })[value] ?? value;
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
