import { useEffect, useMemo, useState } from "react";

import { downloadPageResult, runAnalysis, updateAnalysisSelection } from "./v020_api";
import type { AnalysisRow, RunEvidence, WorkspaceState } from "./v020_types";
import { visibleRunForPage } from "./v020_run_state";
import { PageHeader } from "./UploadWorkspace";
import { RequirementPointTable } from "./RequirementPointTable";
import { WorkflowRunControls } from "./WorkflowRunControls";

const emptyFilters = { keyword: "", module: "", testItem: "", source: "", selected: "", status: "" };

export function AnalysisWorkspace({ projectId, workspace, onChanged }: {
  projectId: number; workspace: WorkspaceState; onChanged: () => Promise<void>;
}) {
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selection, setSelection] = useState<Record<string, boolean>>(() => selectionMap(workspace.analysis_rows));
  const [completedResult, setCompletedResult] = useState<{ run: RunEvidence; rows: AnalysisRow[] } | null>(null);
  const [error, setError] = useState("");
  const analysisRows = completedResult?.rows ?? workspace.analysis_rows;
  useEffect(() => setSelection(selectionMap(analysisRows)), [analysisRows]);
  useEffect(() => {
    if (completedResult && (
      workspace.active_run_ids?.analysis === completedResult.run.id
      || workspace.analysis_rows.some((row) => row.run_id === completedResult.run.id)
    )) setCompletedResult(null);
  }, [completedResult, workspace.active_run_ids, workspace.analysis_rows]);
  useEffect(() => setCompletedResult(null), [projectId]);
  const displayRows = useMemo(() => analysisRows.map((row) => ({
    ...row, selected: selection[row.id] ?? row.selected,
  })), [analysisRows, selection]);
  const filtered = useMemo(() => displayRows.filter((row) => matches(row, filters)), [displayRows, filters]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const selectedCount = displayRows.filter((row) => row.selected).length;
  const latestRun = completedResult?.run ?? visibleRunForPage(workspace, "analysis");
  const setFilter = (name: keyof typeof emptyFilters, value: string) => { setFilters({ ...filters, [name]: value }); setPage(1); };
  const updateRows = async (ids: string[], selected: boolean) => {
    if (!ids.length) return;
    const previous = selection;
    setSelection((current) => ({ ...current, ...Object.fromEntries(ids.map((id) => [id, selected])) }));
    try { await updateAnalysisSelection(projectId, ids, selected); await onChanged(); }
    catch (reason) { setSelection(previous); setError(message(reason)); }
  };
  const selectFiltered = async () => {
    if (!window.confirm(`将勾选当前筛选命中的 ${filtered.length} 项，是否继续？`)) return;
    await updateRows(filtered.map((row) => row.id), true);
  };
  return <section className="workflow-page">
    <PageHeader title="需求分析" subtitle="按宽泛模块整理可验证测试项，并记录依据、来源、测试类型和关联需求；你的勾选就是正式测试用例范围。" />
    <WorkflowRunControls projectId={projectId} page="analysis" actionLabel="开始需求分析" latestRun={latestRun}
      allowedModes={["skill", "local"]} defaultMode="skill"
      onRunSettled={onChanged}
      disabled={!workspace.requirement_version} onRun={async (mode, confirmed, runId) => {
        const result = await runAnalysis(projectId, mode, confirmed, runId);
        setCompletedResult({ run: result.run, rows: result.rows });
        setFilters(emptyFilters); setPage(1);
        return result;
      }} />
    <div className="action-row"><button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "analysis", "xlsx")}>下载需求分析表（Excel）</button>
      <button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "analysis", "json")}>下载 JSON</button>
      <strong>已选 {selectedCount} 项，这些内容将用于生成测试用例</strong></div>
    <RunComparison workspace={workspace} />
    <section className="filter-bar" aria-label="需求分析筛选">
      <Filter label="关键词"><input value={filters.keyword} placeholder="模块、测试项或关联需求 ID" onChange={(e) => setFilter("keyword", e.target.value)} /></Filter>
      <SelectFilter label="功能模块" value={filters.module} values={unique(analysisRows, "module")} onChange={(v) => setFilter("module", v)} />
      <SelectFilter label="测试项" value={filters.testItem} values={unique(analysisRows, "test_item")} onChange={(v) => setFilter("testItem", v)} />
      <SelectFilter label="来源" value={filters.source} values={unique(analysisRows, "source")} onChange={(v) => setFilter("source", v)} />
      <Filter label="勾选状态"><select value={filters.selected} onChange={(e) => setFilter("selected", e.target.value)}><option value="">全部</option><option value="yes">已选</option><option value="no">未选</option></select></Filter>
      <Filter label="分析状态"><select value={filters.status} onChange={(e) => setFilter("status", e.target.value)}><option value="">全部</option><option value="ready">可使用</option><option value="needs_information">信息不足</option></select></Filter>
      <button type="button" className="secondary" onClick={() => { setFilters(emptyFilters); setPage(1); }}>清除筛选</button>
      <button type="button" className="secondary" onClick={() => void updateRows(visible.map((row) => row.id), true)}>全选本页</button>
      <button type="button" className="secondary" onClick={() => void selectFiltered()}>全选当前筛选结果（{filtered.length}）</button>
    </section>
    <RequirementPointTable rows={visible} selectable
      onSelectionChange={(id, selected) => void updateRows([id], selected)} />
    <Pagination total={analysisRows.length} filtered={filtered.length} page={currentPage} pageSize={pageSize}
      setPage={setPage} setPageSize={(value) => { setPageSize(value); setPage(1); }} />
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

function RunComparison({ workspace }: { workspace: WorkspaceState }) {
  const runs = workspace.runs.filter((run) => run.page === "analysis" && run.status === "completed");
  const historyRows = workspace.analysis_history_rows ?? workspace.analysis_rows;
  const direct = [...runs].reverse().find((run) => run.mode === "direct");
  const skill = [...runs].reverse().find((run) => run.mode === "skill");
  if (!direct && !skill) return null;
  return <details className="comparison-card"><summary>比较最近一次直接调用与 Skill 工作流</summary><div>
    {[direct, skill].map((run, index) => <article key={run?.id ?? index}><strong>{run?.source_label ?? (index ? "Skill 工作流未运行" : "直接调用未运行")}</strong>
      {run && <><span>{run.result_summary?.count ?? 0} 条结果</span><span>耗时 {((run.duration_ms ?? 0) / 1000).toFixed(1)} 秒</span>
        <span>{run.actual_usage?.status === "available" ? `${run.actual_usage.total_tokens ?? "-"} Token` : "实际 Token 不可获得"}</span>
        <ul>{historyRows.filter((row) => row.run_id === run.id).slice(0, 5).map((row) =>
          <li key={row.id}>{row.module} / {row.test_item} / {row.test_type}</li>)}</ul></>}</article>)}</div></details>;
}
function matches(row: AnalysisRow, filters: typeof emptyFilters): boolean {
  const keyword = filters.keyword.trim().toLowerCase();
  return (!keyword || [row.module, row.test_item, row.related_requirement_id].some((v) => v.toLowerCase().includes(keyword)))
    && (!filters.module || row.module === filters.module)
    && (!filters.testItem || row.test_item === filters.testItem) && (!filters.source || row.source === filters.source)
    && (!filters.selected || row.selected === (filters.selected === "yes")) && (!filters.status || row.status === filters.status);
}
const unique = (rows: AnalysisRow[], key: keyof AnalysisRow): string[] => [...new Set(rows.map((row) => String(row[key])))].filter(Boolean);
const selectionMap = (rows: AnalysisRow[]): Record<string, boolean> => Object.fromEntries(rows.map((row) => [row.id, row.selected]));
function Filter({ label, children }: { label: string; children: React.ReactNode }) { return <label>{label}{children}</label>; }
function SelectFilter({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (value: string) => void }) {
  return <Filter label={label}><select value={value} onChange={(e) => onChange(e.target.value)}><option value="">全部</option>{values.map((item) => <option key={item}>{item}</option>)}</select></Filter>;
}
export function Pagination({ total, filtered, page, pageSize, setPage, setPageSize }: { total: number; filtered: number; page: number; pageSize: number; setPage: (value: number) => void; setPageSize: (value: number) => void }) {
  const pages = Math.max(1, Math.ceil(filtered / pageSize)); const start = filtered ? (page - 1) * pageSize + 1 : 0; const end = Math.min(filtered, page * pageSize);
  return <footer className="pagination"><span>共 {total} 条、当前筛选命中 {filtered} 条、本页 {start}–{end} 条</span>
    <label>每页<select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>{[20, 50, 100].map((value) => <option key={value}>{value}</option>)}</select> 条</label>
    <button type="button" className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button><strong>第 {page} / {pages} 页</strong>
    <button type="button" className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>下一页</button></footer>;
}
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
