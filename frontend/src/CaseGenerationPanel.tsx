import { useMemo, useState } from "react";

import { CandidateTestCase, CaseGeneration, editCase, generateCases } from "./api";
import { CaseReviewPanel } from "./CaseReviewPanel";

export function CaseGenerationPanel({ projectId }: { projectId: number }) {
  const [designId, setDesignId] = useState(1);
  const [mappingId, setMappingId] = useState(1);
  const [generation, setGeneration] = useState<CaseGeneration | null>(null);
  const [error, setError] = useState("");
  const [strictConflicts, setStrictConflicts] = useState(false);
  const [modules, setModules] = useState("");
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [removed, setRemoved] = useState<string[]>([]);
  const [editedIds, setEditedIds] = useState<string[]>([]);
  const [moduleFilter, setModuleFilter] = useState("all");
  const [testItemFilter, setTestItemFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("included");
  const [page, setPage] = useState(1);

  const generate = async () => {
    try {
      const created = await generateCases(
        projectId, designId, mappingId, false, strictConflicts,
        modules.split(",").map((item) => item.trim()).filter(Boolean),
      );
      setGeneration(created);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "候选测试用例生成失败");
    }
  };

  const filteredCandidates = useMemo(() => (generation?.candidates ?? []).filter((candidate) => {
    const matchesSearch = !search || `${candidate.title} ${candidate.module ?? ""} ${candidate.test_item ?? ""}`
      .toLowerCase().includes(search.toLowerCase());
    const isRemoved = removed.includes(candidate.id);
    return matchesSearch && (priority === "all" || candidate.priority === priority)
      && (moduleFilter === "all" || candidate.module === moduleFilter)
      && (testItemFilter === "all" || candidate.test_item === testItemFilter)
      && (statusFilter === "all" || (statusFilter === "removed") === isRemoved);
  }), [generation, moduleFilter, priority, removed, search, statusFilter, testItemFilter]);
  const visibleCandidates = filteredCandidates.slice((page - 1) * 10, page * 10);
  const modulesForFilter = [...new Set((generation?.candidates ?? []).map((candidate) => candidate.module).filter(Boolean))];
  const testItemsForFilter = [...new Set((generation?.candidates ?? []).map((candidate) => candidate.test_item).filter(Boolean))];

  const updateTitle = (candidateId: string, title: string) => setGeneration((current) => current && {
    ...current, candidates: current.candidates.map((candidate) => candidate.id === candidateId
      ? { ...candidate, title } : candidate),
  });

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

  const removeSelected = () => {
    setRemoved((current) => [...new Set([...current, ...selected])]);
    setSelected([]);
  };

  return <section className="panel" aria-label="候选测试用例生成">
    <h2>生成可追踪的候选测试用例</h2>
    <label>已确认测试设计编号
      <input type="number" min="1" value={designId} onChange={(event) => setDesignId(Number(event.target.value))} />
    </label>
    <label>已确认模板映射编号
      <input type="number" min="1" value={mappingId} onChange={(event) => setMappingId(Number(event.target.value))} />
    </label>
    <button onClick={() => void generate()}>生成候选测试用例</button>
    <label><input type="checkbox" checked={strictConflicts} onChange={(event) => setStrictConflicts(event.target.checked)} /> 整批严格模式</label>
    <label>局部生成模块（逗号分隔）<input value={modules} onChange={(event) => setModules(event.target.value)} /></label>
    {error && <p role="alert" className="error">{error}</p>}
    {generation && <div>
      <p role="status">
        生成状态：{generation.status}；AI 运行编号：{generation.ai_run_id}；
        {generation.is_mock ? "Mock AI 运行" : "真实 AI 运行"}（{generation.ai_run_status}）
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
        <button onClick={removeSelected} disabled={selected.length === 0}>批量移除</button>
        {removed.length > 0 && <button onClick={() => setRemoved([])}>恢复已移除用例</button>}
      </div>
      <p>用例表预览：显示 {visibleCandidates.length} / {filteredCandidates.length} 条，已移除 {removed.length} 条</p>
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
        </article>)}
      </div>
      {generation.candidates.length > 0 && <CaseReviewPanel
        projectId={projectId}
        generationId={generation.id}
        candidateIds={generation.candidates.map((candidate) => candidate.id)}
        excludedCandidateIds={removed}
        candidates={generation.candidates}
        editedIds={editedIds}
      />}
    </div>}
  </section>;
}
