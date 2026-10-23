import { useEffect, useMemo, useState } from "react";

import { TemplateMappingPanel } from "./TemplateMappingPanel";
import { CaseTemplatePreview } from "./CaseTemplatePreview";
import { Pagination } from "./AnalysisWorkspace";
import { downloadDefaultCaseTemplate, downloadPageResult, editV020Case, getCaseTemplate, runCases, selectCaseTemplate,
  setV020CaseInclusion, setV020CaseRemoved } from "./v020_api";
import type { CaseTemplateState, GeneratedCase, WorkspaceState } from "./v020_types";
import { visibleRunForPage } from "./v020_run_state";
import { PageHeader } from "./UploadWorkspace";
import { WorkflowRunControls } from "./WorkflowRunControls";

const emptyFilters = { keyword: "", module: "", testItem: "", testPoint: "", priority: "", included: "", mode: "" };

export function CaseWorkspace({ projectId, workspace, onChanged }: {
  projectId: number; workspace: WorkspaceState; onChanged: () => Promise<void>;
}) {
  const [template, setTemplate] = useState<CaseTemplateState | null>(null);
  const [requirements, setRequirements] = useState("");
  const [filters, setFilters] = useState(emptyFilters);
  const [generation, setGeneration] = useState("current");
  const [page, setPage] = useState(1); const [pageSize, setPageSize] = useState(20);
  const [editing, setEditing] = useState<GeneratedCase | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { void getCaseTemplate(projectId).then(setTemplate).catch((reason) => setError(message(reason))); },
    [projectId, workspace.template.mode, workspace.template.mapping_id]);
  const selectedRows = workspace.analysis_rows.filter((row) => row.selected);
  const generationIds = workspace.case_generations.map((item) => item.id);
  const currentGenerationRecord = workspace.active_run_ids
    ? workspace.case_generations.find((item) => item.run_id === workspace.active_run_ids?.cases)
    : workspace.case_generations.at(-1);
  const currentGeneration = currentGenerationRecord?.id;
  const selectedGeneration = generation === "current" ? currentGeneration : generation;
  const selectedGenerationRecord = workspace.case_generations.find((item) => item.id === selectedGeneration);
  const cases = useMemo(() => workspace.cases.filter((item) => {
    const belongsToGeneration = generation === "current"
      ? Boolean(selectedGeneration) && item.generation_id === selectedGeneration
      : item.generation_id === selectedGeneration;
    return belongsToGeneration && matches(item, filters);
  }), [workspace.cases, filters, generation, selectedGeneration]);
  const pageCount = Math.max(1, Math.ceil(cases.length / pageSize)); const currentPage = Math.min(page, pageCount);
  const visible = cases.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const latestRun = visibleRunForPage(workspace, "cases");
  const chooseTemplate = async (mode: "default" | "uploaded", mappingId: number | null = null) => {
    try { setTemplate(await selectCaseTemplate(projectId, mode, mappingId)); await onChanged(); }
    catch (reason) { setError(message(reason)); }
  };
  const updateCase = async (caseId: string, update: object) => {
    try { await editV020Case(projectId, caseId, update); setEditing(null); await onChanged(); }
    catch (reason) { setError(message(reason)); }
  };
  return <section className="workflow-page">
    <PageHeader title="测试用例" subtitle="模板、已选范围、生成模式、预览编辑和导出全部在本页完成。" />
    <fieldset className="numbered-section template-picker"><legend>1. 测试用例模板</legend>
      <label><input type="radio" name="case-template" checked={(template?.mode ?? "default") === "default"}
        onChange={() => void chooseTemplate("default")} /> 使用默认测试用例模板</label>
      <label><input type="radio" name="case-template" checked={template?.mode === "uploaded"}
        onChange={() => setTemplate((current) => ({ mode: "uploaded", mapping: current?.mode === "uploaded" ? current.mapping : null }))} /> 上传测试用例模板</label>
      <button type="button" className="secondary" onClick={() => void downloadDefaultCaseTemplate(projectId)}>下载默认测试模板</button>
      {template?.mapping && <details open><summary>查看模板字段解析与映射</summary>
        <p>{template.mapping.filename} · {template.mapping.status === "confirmed" ? "映射已确认" : "待确认"}</p>
        {template.mapping.sheets.map((sheet) => <p key={sheet.name}><strong>{sheet.name}</strong>：{Object.entries(sheet.field_mapping).map(([column, field]) => `${column}→${field}`).join("，") || "暂无映射"}</p>)}</details>}
      {template?.mode === "uploaded" && !template.mapping && <TemplateMappingPanel projectId={projectId}
        onConfirmed={(mapping) => void chooseTemplate("uploaded", mapping.id)} />}
    </fieldset>
    <section className="numbered-section scope-summary"><strong>2. 当前测试范围</strong>
      <span>已选 {selectedRows.length} 个测试点{selectedRows.length ? `：${selectedRows.slice(0, 3).map((row) => row.test_point).join("、")}${selectedRows.length > 3 ? "…" : ""}` : "；请先到需求分析页勾选"}</span></section>
    <section className="numbered-section"><strong>3. 生成模式</strong>
      <WorkflowRunControls projectId={projectId} page="cases" actionLabel="生成测试用例" latestRun={latestRun}
        onRunSettled={onChanged}
        disabled={!selectedRows.length || !template?.mapping}
        templateMode={template?.mode ?? "default"} templateMappingId={template?.mode === "uploaded" ? template.mapping?.id ?? null : null}
        supplementalRequirements={requirements}
        beforeAction={<label className="field-stack"><strong>4. 补充生成要求（可选）</strong><textarea value={requirements}
          placeholder="例如：优先输出 P0/P1；每个边界场景独立成用例。" onChange={(event) => setRequirements(event.target.value)} /></label>}
        onRun={async (mode, confirmed, runId) => runCases(projectId, mode, confirmed, template?.mode ?? "default",
          template?.mode === "uploaded" ? template.mapping?.id ?? null : null, requirements, runId)} /></section>
    <div className="action-row"><button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "cases", "xlsx")}>导出 Excel</button>
      <button type="button" className="secondary" onClick={() => void downloadPageResult(projectId, "cases", "json")}>导出 JSON</button></div>
    <section className="case-results"><header><div><h3>候选测试用例</h3><p>支持本次生成与历史记录、筛选分页、编辑、移除恢复和纳入选择。</p></div>
      <label>查看<select value={generation} onChange={(event) => { setGeneration(event.target.value); setPage(1); }}><option value="current">本次生成</option>
        {generationIds.filter((id) => id !== currentGeneration).reverse().map((id) => { const record = workspace.case_generations.find((item) => item.id === id);
          const run = workspace.runs.find((item) => item.id === record?.run_id); return <option key={id} value={id}>
            {new Date(record?.created_at ?? "").toLocaleString()} · {modeLabel(run?.mode ?? "")} · {record?.scope_ids.length ?? 0} 项范围
          </option>; })}</select></label></header>
      <CaseFilters cases={workspace.cases} filters={filters} setFilters={(next) => { setFilters(next); setPage(1); }} />
      <CaseTemplatePreview mapping={selectedGenerationRecord?.template ?? template?.mapping} cases={visible}
        onToggle={(item, included) => void setV020CaseInclusion(projectId, item.id, included).then(onChanged)}
        onEdit={setEditing}
        onRemove={(item) => void setV020CaseRemoved(projectId, item.id, !item.removed).then(onChanged)} />
      <Pagination total={workspace.cases.length} filtered={cases.length} page={currentPage} pageSize={pageSize} setPage={setPage}
        setPageSize={(value) => { setPageSize(value); setPage(1); }} />
      <p className="quality-hint">质量提示：{qualityHint(cases)}</p>
    </section>
    {editing && <CaseEditor value={editing} onCancel={() => setEditing(null)} onSave={(update) => void updateCase(editing.id, update)} />}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

function CaseFilters({ cases, filters, setFilters }: { cases: GeneratedCase[]; filters: typeof emptyFilters; setFilters: (value: typeof emptyFilters) => void }) {
  const field = (key: keyof typeof emptyFilters, value: string) => setFilters({ ...filters, [key]: value });
  return <section className="filter-bar" aria-label="测试用例筛选"><label>关键词<input value={filters.keyword} placeholder="标题或测试点" onChange={(e) => field("keyword", e.target.value)} /></label>
    {(["module", "testItem", "testPoint", "priority", "mode"] as const).map((key) => <label key={key}>{({ module: "功能模块", testItem: "测试项", testPoint: "测试点", priority: "优先级", mode: "生成方式" })[key]}
      <select value={filters[key]} onChange={(e) => field(key, e.target.value)}><option value="">全部</option>
        {[...new Set(cases.map((item) => String(({ module: item.module, testItem: item.test_item, testPoint: item.test_point, priority: item.priority, mode: item.mode })[key] ?? "")))].filter(Boolean).map((value) => <option key={value}>{value}</option>)}</select></label>)}
    <label>纳入状态<select value={filters.included} onChange={(e) => field("included", e.target.value)}><option value="">全部</option><option value="yes">已纳入</option><option value="no">未纳入</option></select></label>
    <button type="button" className="secondary" onClick={() => setFilters(emptyFilters)}>清除筛选</button></section>;
}
function CaseEditor({ value, onCancel, onSave }: { value: GeneratedCase; onCancel: () => void; onSave: (update: object) => void }) {
  const [title, setTitle] = useState(value.title); const [priority, setPriority] = useState(value.priority);
  return <div className="modal-backdrop"><section className="modal-card" role="dialog" aria-modal="true" aria-label="编辑候选测试用例"><h2>编辑候选测试用例</h2>
    <label className="field-stack">标题<input value={title} onChange={(e) => setTitle(e.target.value)} /></label><label className="field-stack">优先级<select value={priority} onChange={(e) => setPriority(e.target.value as GeneratedCase["priority"])}>{["P0", "P1", "P2", "P3"].map((item) => <option key={item}>{item}</option>)}</select></label>
    <div className="action-row"><button type="button" onClick={() => onSave({ title, priority })}>保存编辑</button><button type="button" className="secondary" onClick={onCancel}>取消</button></div></section></div>;
}
function matches(item: GeneratedCase, filters: typeof emptyFilters): boolean { const keyword = filters.keyword.toLowerCase();
  return (!keyword || [item.title, item.test_point ?? ""].some((value) => value.toLowerCase().includes(keyword)))
    && (!filters.module || item.module === filters.module) && (!filters.testItem || item.test_item === filters.testItem)
    && (!filters.testPoint || item.test_point === filters.testPoint) && (!filters.priority || item.priority === filters.priority)
    && (!filters.mode || item.mode === filters.mode) && (!filters.included || (item.included && !item.removed) === (filters.included === "yes")); }
const qualityHint = (cases: GeneratedCase[]) => cases.length && cases.every((item) => item.steps.length && item.overall_expectation) ? "当前候选均包含步骤与整体预期；仍需人工确认业务正确性。" : "部分候选缺少可执行步骤或预期，请编辑后再导出。";
const modeLabel = (value: string) => ({ direct: "直接调用", skill: "Skill 工作流", local: "本地模式" })[value] ?? value;
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
