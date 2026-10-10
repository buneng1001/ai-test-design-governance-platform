import { useCallback, useEffect, useMemo, useState } from "react";

import { AnalysisWorkspace } from "./AnalysisWorkspace";
import { CaseWorkspace } from "./CaseWorkspace";
import { ModelAccessCard } from "./ModelAccessCard";
import { ReviewWorkspace } from "./ReviewWorkspace";
import { SuggestionsWorkspace } from "./SuggestionsWorkspace";
import { UploadWorkspace } from "./UploadWorkspace";
import { downloadDeliveryPackage, downloadPageResult, getV020Workspace } from "./v020_api";
import type { RunEvidence, WorkspaceState } from "./v020_types";
import "./v020-workflow.css";

type TabId = "upload" | "analysis" | "suggestions" | "review" | "cases";
const tabs: Array<{ id: TabId; label: string }> = [
  { id: "upload", label: "上传文档" }, { id: "analysis", label: "需求分析" },
  { id: "suggestions", label: "新增建议" }, { id: "review", label: "审核" },
  { id: "cases", label: "测试用例" },
];

export function WorkflowShell({ projectId, projectName, testObject, softwareVersion, onOpenProjects }: {
  projectId: number; projectName: string; testObject: string; softwareVersion: string; onOpenProjects: () => void;
}) {
  const [workspace, setWorkspace] = useState<WorkspaceState | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("upload");
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try { setWorkspace(await getV020Workspace(projectId)); setError(""); }
    catch (reason) { setError(message(reason)); }
  }, [projectId]);
  useEffect(() => { void refresh(); }, [refresh]);
  if (!workspace) return <p role={error ? "alert" : undefined} className={error ? "error" : "muted"}>
    {error || "正在恢复项目资料、分析范围和测试用例…"}</p>;
  const selected = workspace.analysis_rows.filter((row) => row.selected).length;
  return <section className="formal-workspace">
    <section className="project-bar"><div><small>当前测试设计项目</small><strong>{projectName}</strong>
      <span>{testObject} · {softwareVersion} · 需求版本 {workspace.requirement_version ? `V${workspace.requirement_version.version}` : "未建立"} · 已选测试点 {selected}</span></div>
      <div><button type="button" className="secondary" onClick={onOpenProjects}>项目管理</button>
        <button type="button" className="secondary" onClick={() => void downloadDeliveryPackage(projectId).catch((reason) => setError(message(reason)))}>下载项目交付包</button></div></section>
    <header className="product-bar"><div><strong>AI 测试用例生成平台</strong><span>上传文档 → 需求分析 → 新增建议 → 审核 → 测试用例</span></div></header>
    <nav className="workflow-tab-strip" role="tablist" aria-label="主流程页签">{tabs.map((tab, index) => <button type="button" role="tab"
      key={tab.id} aria-selected={activeTab === tab.id} className={activeTab === tab.id ? "selected" : ""} onClick={() => setActiveTab(tab.id)}>
      <small>{index + 1}</small>{tab.label}</button>)}</nav>
    <div className="workspace-columns"><aside className="workspace-context"><section className="context-section"><h3>当前项目</h3>
      <p>{projectName}</p><p>已解析：{workspace.requirement_version?.materials.length ?? 0} 份资料</p><p>已选测试点：{selected} 项</p>
      <p>候选用例：{workspace.cases.length} 条</p></section><ModelAccessCard /><RunHistory projectId={projectId} runs={workspace.runs} /></aside>
      <main className="workspace-main">
        {activeTab === "upload" && <UploadWorkspace projectId={projectId} workspace={workspace} onChanged={refresh} />}
        {activeTab === "analysis" && <AnalysisWorkspace projectId={projectId} workspace={workspace} onChanged={refresh} />}
        {activeTab === "suggestions" && <SuggestionsWorkspace projectId={projectId} workspace={workspace} onChanged={refresh} />}
        {activeTab === "review" && <ReviewWorkspace projectId={projectId} workspace={workspace} onChanged={refresh} onSkip={() => setActiveTab("cases")} />}
        {activeTab === "cases" && <CaseWorkspace projectId={projectId} workspace={workspace} onChanged={refresh} />}
        {error && <p role="alert" className="error">{error}</p>}
      </main></div>
  </section>;
}

function RunHistory({ projectId, runs }: { projectId: number; runs: RunEvidence[] }) {
  const [page, setPage] = useState(""); const [mode, setMode] = useState(""); const [status, setStatus] = useState("");
  const [date, setDate] = useState("");
  const filtered = useMemo(() => [...runs].reverse().filter((run) => (!page || run.page === page) && (!mode || run.mode === mode)
    && (!status || run.status === status) && (!date || run.started_at.startsWith(date))), [runs, page, mode, status, date]);
  return <details className="run-history"><summary>项目 AI / 本地运行历史（{runs.length}）</summary>
    <div className="history-filters"><label>页面<select value={page} onChange={(e) => setPage(e.target.value)}><option value="">全部</option>{["analysis", "suggestions", "review", "cases"].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>方式<select value={mode} onChange={(e) => setMode(e.target.value)}><option value="">全部</option>{["direct", "skill", "local"].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>状态<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">全部</option>{["completed", "failed", "running"].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>日期<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label></div>
    <ul className="history-list">{filtered.map((run) => <li key={run.id}><details><summary><strong>{pageLabel(run.page)} · {modeLabel(run.mode)}</strong></summary>
      <span>{new Date(run.started_at).toLocaleString()} · {statusLabel(run.status)} · {run.model}</span>
      <small>{run.result_summary ? `${run.result_summary.count} ${run.result_summary.label}` : run.error ?? "运行中"}</small>
      <small>范围：{run.input_summary.analysis_row_count || run.input_summary.fragment_count} 项，已选 {run.input_summary.selected_row_count} 项 · 耗时 {run.duration_ms === null ? "运行中" : `${(run.duration_ms / 1000).toFixed(1)} 秒`}</small>
      {run.status === "completed" && <div className="table-actions"><button type="button" className="text-button"
        onClick={() => void downloadPageResult(projectId, run.page, "json", run.id)}>下载本次 JSON</button>
        <button type="button" className="text-button" onClick={() => void downloadPageResult(projectId, run.page, "xlsx", run.id)}>下载本次 Excel</button></div>}
    </details></li>)}</ul>
    {!filtered.length && <p className="empty-hint">没有符合筛选条件的运行记录。</p>}
  </details>;
}
const pageLabel = (value: string) => ({ analysis: "需求分析", suggestions: "新增建议", review: "审核", cases: "测试用例" })[value] ?? value;
const modeLabel = (value: string) => ({ direct: "直接调用", skill: "Skill 工作流", local: "本地模式" })[value] ?? value;
const statusLabel = (value: string) => ({ completed: "已完成", failed: "失败", running: "正在执行" })[value] ?? value;
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
