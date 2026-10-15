import { useState } from "react";

import { disposeReviewSuggestion, downloadPageResult, runReview, skipReview } from "./v020_api";
import type { WorkspaceState } from "./v020_types";
import { PageHeader } from "./UploadWorkspace";
import { RequirementPointTable } from "./RequirementPointTable";
import { WorkflowRunControls } from "./WorkflowRunControls";

const roleLabels = { product_manager: "产品经理", project_manager: "项目经理", test_manager: "测试经理" };

export function ReviewWorkspace({ projectId, workspace, onChanged, onSkip }: {
  projectId: number; workspace: WorkspaceState; onChanged: () => Promise<void>; onSkip: () => void;
}) {
  const [roles, setRoles] = useState<string[]>(["test_manager"]);
  const [error, setError] = useState("");
  const latestRun = workspace.active_run_ids
    ? workspace.runs.find((run) => run.id === workspace.active_run_ids?.review)
    : [...workspace.runs].reverse().find((run) => run.page === "review");
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
      onRun={async (mode, confirmed) => {
        const result = await runReview(projectId, mode, confirmed, roles); await onChanged(); return result;
      }} />
    <div className="action-row"><button type="button" className="secondary" onClick={() => void skip()}>跳过审核，进入测试用例</button>
      <button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "review", "json")}>下载审核报告</button></div>
    {latestRun?.role_reports?.length ? <section className="review-report" aria-label="身份需求分析报告">
      <h3>身份需求分析报告</h3>{latestRun.role_reports.map((report) => <article key={report.role}>
        <h4>{roleLabels[report.role as keyof typeof roleLabels] ?? report.role}</h4><p>{report.summary}</p>
        {!!report.strengths.length && <p><strong>已有基础：</strong>{report.strengths.join("；")}</p>}
        {!!report.concerns.length && <p><strong>关注事项：</strong>{report.concerns.join("；")}</p>}
      </article>)}</section> : null}
    <section aria-label="审核建议结果">
      {!workspace.review_suggestions.length && <p className="empty-hint">尚未执行审核；可以直接跳过。</p>}
      <RequirementPointTable rows={[...workspace.review_suggestions].reverse().map((item, index) => ({
        ...item, total_index: index + 1,
        test_basis: `${roleLabels[item.role as keyof typeof roleLabels] ?? item.role}：${item.test_basis}`,
        action: <div className="table-actions"><span className={`status-pill ${item.disposition}`}>
          {actionLabel(item.suggestion_action)} · {dispositionLabel(item.disposition)}</span>
          {item.disposition === "pending" && <><button type="button" className="text-button" onClick={() => void dispose(item.id, "accepted")}>接纳并回流</button>
            <button type="button" className="text-button" onClick={() => void dispose(item.id, "rejected")}>不接纳</button></>}</div>,
      }))} />
    </section>
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

const actionLabel = (value: string) => ({ add: "建议增加", remove: "建议减少", risk: "风险项" })[value] ?? value;
const dispositionLabel = (value: string) => ({ pending: "待处置", accepted: "已接纳", rejected: "不接纳" })[value] ?? value;
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
