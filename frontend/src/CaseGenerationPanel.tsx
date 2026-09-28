import { useEffect, useMemo, useState } from "react";

import {
  advanceCaseGenerationRun, CandidateTestCase, CaseGeneration, editGeneratedCase, getCaseGeneration,
  isAIRunControl, resumeCaseGenerationRun, setGeneratedCaseRemoved, startCaseGenerationRun, stopAIRunControl,
} from "./api";
import { CaseReviewPanel } from "./CaseReviewPanel";
import { usePersistentAIRunControl } from "./usePersistentAIRunControl";

export function CaseGenerationPanel({ projectId, designId = 1 }: { projectId: number; designId?: number }) {
  const [generation, setGeneration] = useState<CaseGeneration | null>(null);
  const [error, setError] = useState("");
  const [strictConflicts, setStrictConflicts] = useState(false);
  const [modules, setModules] = useState("");
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [editedIds, setEditedIds] = useState<string[]>([]);
  const [moduleFilter, setModuleFilter] = useState("all");
  const [testItemFilter, setTestItemFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("included");
  const [page, setPage] = useState(1);
  const [mode, setMode] = useState<"mock" | "real" | "template">("mock");
  const [isRunning, setIsRunning] = useState(false);
  const { runControl, remember } = usePersistentAIRunControl(projectId, `case:${designId}`);

  const runOptions = () => ({
    templateMappingId: 0, acceptTemplateLimitations: false, strictConflicts,
    modules: modules.split(",").map((item) => item.trim()).filter(Boolean), mode,
  });
  useEffect(() => {
    if (!runControl || runControl.status !== "completed" || !runControl.final_asset_id || generation) return;
    void getCaseGeneration(projectId, runControl.final_asset_id).then((result) => {
      setGeneration(result); remember(null);
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法恢复生成结果"));
  }, [generation, projectId, remember, runControl]);

  const startGeneration = async () => {
    try {
      setIsRunning(true); setGeneration(null);
      remember(await startCaseGenerationRun(projectId, designId, runOptions()));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "候选测试用例生成失败");
    } finally { setIsRunning(false); }
  };
  const advanceGeneration = async (control = runControl) => {
    if (!control || isRunning) return;
    try {
      setIsRunning(true); setError("");
      const result = await advanceCaseGenerationRun(projectId, designId, control.id, runOptions());
      if (isAIRunControl(result)) remember(result);
      else { setGeneration(result); remember(null); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "候选测试用例生成失败"); }
    finally { setIsRunning(false); }
  };
  const stopGeneration = async () => {
    if (!runControl) return;
    try { remember(await stopAIRunControl(projectId, runControl.id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "停止生成失败"); }
  };
  const resumeGeneration = async () => {
    if (!runControl || isRunning) return;
    try {
      setIsRunning(true); setError("");
      const result = await resumeCaseGenerationRun(projectId, designId, runControl.id, runOptions());
      if (isAIRunControl(result)) remember(result);
      else { setGeneration(result); remember(null); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "继续生成失败"); }
    finally { setIsRunning(false); }
  };

  const filteredCandidates = useMemo(() => (generation?.candidates ?? []).filter((candidate) => {
    const matchesSearch = !search || `${candidate.title} ${candidate.module ?? ""} ${candidate.test_item ?? ""}`
      .toLowerCase().includes(search.toLowerCase());
    const isRemoved = (generation?.removed_candidate_ids ?? []).includes(candidate.id);
    return matchesSearch && (priority === "all" || candidate.priority === priority)
      && (moduleFilter === "all" || candidate.module === moduleFilter)
      && (testItemFilter === "all" || candidate.test_item === testItemFilter)
      && (statusFilter === "all" || (statusFilter === "removed") === isRemoved);
  }), [generation, moduleFilter, priority, search, statusFilter, testItemFilter]);
  const visibleCandidates = filteredCandidates.slice((page - 1) * 10, page * 10);
  const modulesForFilter = [...new Set((generation?.candidates ?? []).map((candidate) => candidate.module).filter(Boolean))];
  const testItemsForFilter = [...new Set((generation?.candidates ?? []).map((candidate) => candidate.test_item).filter(Boolean))];

  const updateTitle = (candidateId: string, title: string) => {
    setEditedIds((current) => current.includes(candidateId) ? current : [...current, candidateId]);
    setGeneration((current) => current && {
      ...current, candidates: current.candidates.map((candidate) => candidate.id === candidateId
        ? { ...candidate, title } : candidate),
    });
  };

  const updateCandidate = (candidateId: string, update: Partial<CandidateTestCase>) => {
    setEditedIds((current) => current.includes(candidateId) ? current : [...current, candidateId]);
    setGeneration((current) => current && {
      ...current, candidates: current.candidates.map((candidate) => candidate.id === candidateId
        ? { ...candidate, ...update } : candidate),
    });
  };

  const updateSteps = (candidate: CandidateTestCase, text: string, field: "action" | "expected") => {
    const lines = text.split("\n").filter((line) => line.trim());
    updateCandidate(candidate.id, { steps: candidate.steps.map((step, index) => ({
      ...step, [field]: lines[index]?.replace(/^\d+\.\s*/, "") ?? step[field],
    })) });
  };

  const toggleSelected = (candidateId: string) => setSelected((current) => current.includes(candidateId)
    ? current.filter((id) => id !== candidateId) : [...current, candidateId]);

  const saveEdits = async () => {
    if (!generation || editedIds.length === 0) return;
    try {
      let updated = generation;
      for (const candidateId of editedIds) {
        const candidate = updated.candidates.find((item) => item.id === candidateId);
        if (!candidate) continue;
        updated = await editGeneratedCase(projectId, updated.id, candidateId, {
          title: candidate.title, priority: candidate.priority, preconditions: candidate.preconditions,
          input: candidate.input, steps: candidate.steps, overall_expectation: candidate.overall_expectation,
          test_type: candidate.test_type, module: candidate.module, test_item: candidate.test_item,
          pre_test_notes: candidate.pre_test_notes, software_version: candidate.software_version,
          reason: "生成预览中的人工修改",
        });
      }
      setGeneration(updated);
      setEditedIds([]);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "候选用例编辑保存失败");
    }
  };

  const setSelectedRemoval = async (removed: boolean, candidateIds = selected) => {
    if (!generation || candidateIds.length === 0) return;
    try {
      let updated = generation;
      for (const candidateId of candidateIds) {
        updated = await setGeneratedCaseRemoved(projectId, updated.id, candidateId, removed);
      }
      setGeneration(updated);
      setSelected([]);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "候选用例移除状态保存失败");
    }
  };

  return <section className="panel" aria-label="候选测试用例生成">
    <h2 id="case-generation">生成可追踪的候选测试用例</h2>
    <p className="field-help">当前已确认测试设计将使用默认 XLSX 用例模板；用例内容由模型根据已确认测试点生成。</p>
    <label>生成方式<select value={mode} onChange={(event) => setMode(event.target.value as "mock" | "real" | "template")}>
      <option value="mock">Mock AI（离线）</option><option value="real">真实模型</option><option value="template">模板回退（需明确选择）</option>
    </select></label>
    <button disabled={isRunning || Boolean(runControl)} onClick={() => void startGeneration()}>
      {isRunning ? "正在创建…" : "创建用例生成运行"}</button>
    <div className="case-generation-options">
      <label className="checkbox-label"><input type="checkbox" checked={strictConflicts} onChange={(event) => setStrictConflicts(event.target.checked)} /><span>整批严格模式</span></label>
      <label>局部生成模块（逗号分隔）<input value={modules} onChange={(event) => setModules(event.target.value)} /></label>
    </div>
    {runControl && <div className="report-actions" role="status">
      <span>用例生成运行：{runControl.status}；已完成 {runControl.completed_count}/{runControl.batch_total} 批</span>
      {runControl.status === "running" && <><button disabled={isRunning} onClick={() => void advanceGeneration()}>执行下一批</button>
        <button onClick={() => void stopGeneration()}>停止运行</button></>}
      {runControl.status === "stopped" && <button disabled={isRunning} onClick={() => void resumeGeneration()}>继续运行</button>}
    </div>}
    {error && <p role="alert" className="error">{error}</p>}
    {generation && <div>
      <p role="status">
        生成状态：{generation.status}；AI 运行编号：{generation.ai_run_id}；
        {generation.source === "template" ? "模板回退（显式选择）" : generation.is_mock ? "Mock AI 运行" : "真实 AI 运行"}（{generation.ai_run_status}）；
        批次 {generation.completed_batches ?? 1}/{generation.batch_total ?? 1}
      </p>
      <div className="case-table-toolbar">
        <label>搜索用例<input aria-label="搜索用例" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <label>优先级<select aria-label="筛选优先级" value={priority} onChange={(event) => setPriority(event.target.value)}>
          <option value="all">全部优先级</option><option value="P0">P0</option><option value="P1">P1</option>
          <option value="P2">P2</option><option value="P3">P3</option>
        </select></label>
        <label>模块<select aria-label="筛选模块" value={moduleFilter} onChange={(event) => setModuleFilter(event.target.value)}>
          <option value="all">全部模块</option>{modulesForFilter.map((item) => <option key={item}>{item}</option>)}
        </select></label>
        <label>测试项<select aria-label="筛选测试项" value={testItemFilter} onChange={(event) => setTestItemFilter(event.target.value)}>
          <option value="all">全部测试项</option>{testItemsForFilter.map((item) => <option key={item}>{item}</option>)}
        </select></label>
        <label>状态<select aria-label="筛选状态" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="included">当前纳入</option><option value="removed">已移除</option><option value="all">全部状态</option>
        </select></label>
        <button onClick={() => setSelected(visibleCandidates.map((candidate) => candidate.id))}>全选当前结果</button>
        <button onClick={() => void saveEdits()} disabled={editedIds.length === 0}>保存候选编辑</button>
        <button onClick={() => void setSelectedRemoval(true)} disabled={selected.length === 0}>批量移除</button>
        {(generation.removed_candidate_ids ?? []).length > 0 && <button onClick={() => void setSelectedRemoval(
          false, generation.removed_candidate_ids ?? [],
        )}>恢复已移除用例</button>}
      </div>
      <p>用例表预览：显示 {visibleCandidates.length} / {filteredCandidates.length} 条，已移除 {(generation.removed_candidate_ids ?? []).length} 条</p>
      <table className="case-table"><thead><tr><th>选择</th><th>测试用例标题</th><th>优先级</th><th>预置条件</th><th>操作步骤</th><th>预期结果</th><th>软件版本</th></tr></thead>
        <tbody>{visibleCandidates.map((candidate) => <tr key={candidate.id}>
          <td><input type="checkbox" aria-label={`选择-${candidate.id}`} checked={selected.includes(candidate.id)} onChange={() => toggleSelected(candidate.id)} /></td>
          <td><input aria-label={`标题-${candidate.id}`} value={candidate.title} onChange={(event) => updateTitle(candidate.id, event.target.value)} /></td>
          <td><select aria-label={`优先级-${candidate.id}`} value={candidate.priority} onChange={(event) => updateCandidate(candidate.id, {
            priority: event.target.value,
          })}><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select></td>
          <td><textarea aria-label={`预置条件-${candidate.id}`} value={candidate.preconditions.join("\n")} onChange={(event) => updateCandidate(candidate.id, {
            preconditions: event.target.value.split("\n").filter(Boolean),
          })} /><input aria-label={`输入-${candidate.id}`} value={candidate.input ?? ""} onChange={(event) => updateCandidate(candidate.id, { input: event.target.value })} /></td>
          <td><textarea aria-label={`操作步骤-${candidate.id}`} value={candidate.steps.map((step) => `${step.order}. ${step.action}`).join("\n")} onChange={(event) => updateSteps(candidate, event.target.value, "action")} /></td>
          <td><textarea aria-label={`预期结果-${candidate.id}`} value={candidate.steps.map((step) => `${step.order}. ${step.expected}`).join("\n")} onChange={(event) => updateSteps(candidate, event.target.value, "expected")} /></td>
          <td><input aria-label={`测试类型-${candidate.id}`} value={candidate.test_type ?? ""} onChange={(event) => updateCandidate(candidate.id, { test_type: event.target.value })} />
            <input aria-label={`模块-${candidate.id}`} value={candidate.module ?? ""} onChange={(event) => updateCandidate(candidate.id, { module: event.target.value })} />
            <input aria-label={`测试项-${candidate.id}`} value={candidate.test_item ?? ""} onChange={(event) => updateCandidate(candidate.id, { test_item: event.target.value })} />
            <input aria-label={`测试前备注信息-${candidate.id}`} value={candidate.pre_test_notes ?? ""} onChange={(event) => updateCandidate(candidate.id, { pre_test_notes: event.target.value })} />
            <input aria-label={`软件版本-${candidate.id}`} value={candidate.software_version ?? ""} onChange={(event) => updateCandidate(candidate.id, { software_version: event.target.value })} /></td>
        </tr>)}</tbody>
      </table>
      <div className="case-table-toolbar">
        <button disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>上一页</button>
        <span>第 {page} 页</span>
        <button disabled={page * 10 >= filteredCandidates.length} onClick={() => setPage((current) => current + 1)}>下一页</button>
      </div>
      <div className="case-details">
        {visibleCandidates.map((candidate) => <article key={`detail-${candidate.id}`} className="case-card">
          <h3>{candidate.title}</h3>
          <p>目标：{candidate.objective}</p>
          <p>追踪：需求 {candidate.requirement_ids.join("、")}；范围 {candidate.scope_item_id}； 风险 {candidate.risk_item_id}；{candidate.priority}</p>
          <p>设计依据：{candidate.design_basis.map((basis) => basis.reason).join("；")}</p>
          {candidate.pending_confirmations.length > 0 && <p className="error">待确认：{candidate.pending_confirmations.join("；")}</p>}
        </article>)}
      </div>
      {generation.candidates.length > 0 && <CaseReviewPanel
        projectId={projectId}
        generationId={generation.id}
        candidateIds={generation.candidates.map((candidate) => candidate.id)}
        excludedCandidateIds={generation.removed_candidate_ids ?? []}
        candidates={generation.candidates}
        mode={mode === "template" ? "mock" : mode}
      />}
    </div>}
  </section>;
}
