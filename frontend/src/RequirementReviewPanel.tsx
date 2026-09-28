import { useEffect, useMemo, useState } from "react";

import {
  advanceRequirementReviewRun, confirmRequirementReview, decideRequirementConflict, getRequirementReview,
  isAIRunControl, listRequirementVersions, RequirementAnalysis, resumeRequirementReviewRun, startRequirementReviewRun,
  stopAIRunControl, updateFinding, updateRequirementSelection, updateVisualInference,
} from "./api";
import type { RequirementVersion } from "./api_types";
import { usePersistentAIRunControl } from "./usePersistentAIRunControl";

type RequirementReviewPanelProps = {
  projectId: number;
  versionRefreshKey?: number;
  newlyPublishedVersionId?: number | null;
  onWorkflowChanged?: () => void;
};

export function RequirementReviewPanel({
  projectId, versionRefreshKey = 0, newlyPublishedVersionId = null, onWorkflowChanged,
}: RequirementReviewPanelProps) {
  const [analysis, setAnalysis] = useState<RequirementAnalysis | null>(null);
  const [versions, setVersions] = useState<RequirementVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [loadingVersions, setLoadingVersions] = useState(true);
  const [confirmerName, setConfirmerName] = useState("测试工程师");
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"mock" | "real" | "template">("mock");
  const [keyword, setKeyword] = useState("");
  const [moduleFilter, setModuleFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [problemFilter, setProblemFilter] = useState<"all" | "with_problem" | "without_problem">("all");
  const [isRunning, setIsRunning] = useState(false);
  const { runControl, remember } = usePersistentAIRunControl(projectId, `requirement:${selectedVersionId || "pending"}`);

  useEffect(() => {
    void listRequirementVersions(projectId).then((result) => {
      setVersions(result);
      const preferred = newlyPublishedVersionId === null ? undefined : result.find((item) => item.id === newlyPublishedVersionId);
      setSelectedVersionId((current) => String(preferred?.id ?? (current && result.some((item) => String(item.id) === current)
        ? current : result[0]?.id ?? "")));
    }).catch((reason: unknown) => setError(message(reason))).finally(() => setLoadingVersions(false));
  }, [projectId, versionRefreshKey, newlyPublishedVersionId]);

  useEffect(() => {
    if (!runControl || runControl.status !== "completed" || !runControl.final_asset_id || analysis) return;
    void getRequirementReview(projectId, runControl.final_asset_id).then((result) => {
      setAnalysis(result); remember(null);
    }).catch((reason: unknown) => setError(message(reason)));
  }, [analysis, projectId, remember, runControl]);

  const startAnalysis = async () => {
    if (isRunning) return;
    try {
      if (!selectedVersionId) throw new Error("请先发布并选择需求版本");
      setIsRunning(true); setError("");
      setAnalysis(null);
      remember(await startRequirementReviewRun(projectId, Number(selectedVersionId), { mode }));
    } catch (reason) { setError(message(reason)); } finally { setIsRunning(false); }
  };
  const advanceAnalysis = async (control = runControl) => {
    if (!control || isRunning) return;
    try {
      setIsRunning(true); setError("");
      const result = await advanceRequirementReviewRun(projectId, Number(selectedVersionId), control.id, { mode });
      if (isAIRunControl(result)) remember(result);
      else { setAnalysis(result); remember(null); }
    } catch (reason) { setError(message(reason)); } finally { setIsRunning(false); }
  };
  const stopAnalysis = async () => {
    if (!runControl) return;
    try { remember(await stopAIRunControl(projectId, runControl.id)); }
    catch (reason) { setError(message(reason)); }
  };
  const resumeAnalysis = async () => {
    if (!runControl || isRunning) return;
    try {
      setIsRunning(true); setError("");
      const result = await resumeRequirementReviewRun(projectId, Number(selectedVersionId), runControl.id, { mode });
      if (isAIRunControl(result)) remember(result);
      else { setAnalysis(result); remember(null); }
    } catch (reason) { setError(message(reason)); } finally { setIsRunning(false); }
  };
  const refresh = (request: Promise<RequirementAnalysis>) => {
    void request.then((result) => {
      setAnalysis(result);
      setError("");
      if (result.status === "confirmed") onWorkflowChanged?.();
    }).catch((reason: unknown) => setError(message(reason)));
  };

  const modules = useMemo(() => [...new Set((analysis?.requirements ?? []).map((item) => item.module))], [analysis]);
  const types = useMemo(() => [...new Set((analysis?.requirements ?? []).map((item) => item.requirement_type))], [analysis]);
  const selected = new Set(analysis?.selected_requirement_ids ?? []);
  const rowHasProblem = (requirement: RequirementAnalysis["requirements"][number]) => {
    const sourceIds = new Set(requirement.source_references.map((source) => source.reference_id));
    return (analysis?.findings ?? []).some((item) => item.status === "pending_confirmation"
      && (item.source_reference === null || (item.source_reference.reference_id !== undefined
        && sourceIds.has(item.source_reference.reference_id))))
      || (analysis?.visual_inferences ?? []).some((item) => item.decision === "pending_confirmation"
        && sourceIds.has(item.source_reference.reference_id))
      || (analysis?.conflicts ?? []).some((item) => item.affected_modules.includes(requirement.module)
        && ["unresolved", "awaiting_external_confirmation"].includes(item.decision));
  };
  const visibleRequirements = (analysis?.requirements ?? []).filter((item) => {
    const searchable = `${item.name} ${item.statement} ${item.module}`.toLocaleLowerCase();
    const hasProblem = rowHasProblem(item);
    return (!keyword || searchable.includes(keyword.toLocaleLowerCase()))
      && (!moduleFilter || item.module === moduleFilter) && (!typeFilter || item.requirement_type === typeFilter)
      && (problemFilter === "all" || (problemFilter === "with_problem") === hasProblem);
  });
  const blockedCount = (analysis?.requirements ?? []).filter((item) => selected.has(item.requirement_id) && rowHasProblem(item)).length;
  const atomicByRequirementId = new Map((analysis?.atomic_requirements ?? []).map((item) => [item.candidate_id, item]));
  const unassignedFindings = (analysis?.findings ?? []).filter((finding) => finding.source_reference === null);
  const groupedVisibleRequirements = Object.entries(visibleRequirements.reduce<Record<string, typeof visibleRequirements>>(
    (groups, item) => ({ ...groups, [item.module]: [...(groups[item.module] ?? []), item] }), {},
  ));

  return <section className="panel">
    <h2 id="requirement-review">结构预览与需求确认</h2>
    {!analysis && <>
      <label>需求版本<select aria-label="需求版本" value={selectedVersionId} disabled={loadingVersions || !versions.length}
        onChange={(event) => setSelectedVersionId(event.target.value)}>{versions.map((item) =>
          <option key={item.id} value={item.id}>V{item.version} · {item.name}</option>)}</select></label>
      <label>分析方式<select value={mode} onChange={(event) => setMode(event.target.value as "mock" | "real" | "template")}>
        <option value="mock">Mock AI（离线）</option><option value="real">真实模型</option><option value="template">模板回退（需明确选择）</option></select></label>
      <button disabled={loadingVersions || !versions.length || isRunning || Boolean(runControl)} onClick={() => void startAnalysis()}>
        {isRunning ? "正在创建…" : "创建结构分析运行"}</button>
    </>}
    {runControl && <div className="report-actions" role="status">
      <span>分析运行：{runControl.status}；已完成 {runControl.completed_count}/{runControl.batch_total} 批</span>
      {runControl.status === "running" && <><button disabled={isRunning} onClick={() => void advanceAnalysis()}>执行下一批</button>
        <button onClick={() => void stopAnalysis()}>停止运行</button></>}
      {runControl.status === "stopped" && <button disabled={isRunning} onClick={() => void resumeAnalysis()}>继续运行</button>}
    </div>}
    {error && <p role="alert" className="error">{error}</p>}
    {analysis && <>
      <p>状态：{analysis.status === "confirmed" ? "需求已确认" : "等待测试工程师确认"} ·
        已完成 {analysis.analysis_batches?.length ?? 0} 个分析批次 · {analysis.run_source === "template"
          ? " 模板回退（显式选择）" : analysis.is_mock ? " Mock AI" : " 真实模型"}</p>
      {analysis.status === "draft" && <div className="report-actions review-rerun-actions">
        <label>重新分析方式<select value={mode} disabled={isRunning} onChange={(event) => setMode(event.target.value as "mock" | "real" | "template")}>
          <option value="mock">Mock AI（离线）</option><option value="real">真实模型</option><option value="template">模板回退（需明确选择）</option></select></label>
        <button disabled={isRunning || Boolean(runControl)} onClick={() => void startAnalysis()}>{isRunning ? "正在创建…" : "重新分析当前需求版本"}</button>
      </div>}
      <div className="requirement-summary">
        <h3 id="grouped-requirements">需求确认表</h3>
        <p>已选 {selected.size} · 未选 {(analysis.requirements ?? []).length - selected.size} · 阻塞问题 {blockedCount}</p>
        <p className="field-help">只有本表勾选并完成确认的需求会进入后续分析；未勾选项不会进入建议、测试设计、覆盖率或用例生成。</p>
        <div className="filter-grid">
          <label>关键字<input aria-label="关键字" value={keyword} onChange={(event) => setKeyword(event.target.value)} /></label>
          <label>模块<select aria-label="模块筛选" value={moduleFilter} onChange={(event) => setModuleFilter(event.target.value)}>
            <option value="">全部模块</option>{modules.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>类型<select aria-label="类型筛选" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <option value="">全部类型</option>{types.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>问题状态<select aria-label="问题状态" value={problemFilter}
            onChange={(event) => setProblemFilter(event.target.value as typeof problemFilter)}>
            <option value="all">全部</option><option value="with_problem">有问题</option><option value="without_problem">无问题</option></select></label>
        </div>
        {analysis.status === "draft" && <div className="button-group">
          <button onClick={() => refresh(updateRequirementSelection(projectId, analysis.id, [
            ...new Set([...selected, ...visibleRequirements.map((item) => item.requirement_id)]),
          ]))}>选择当前筛选结果</button>
          <button onClick={() => refresh(updateRequirementSelection(projectId, analysis.id, [...selected].filter(
            (id) => !visibleRequirements.some((item) => item.requirement_id === id),
          )))}>取消当前筛选结果</button>
        </div>}
        {visibleRequirements.length === 0 && <p className="muted">没有符合当前筛选条件的需求。</p>}
        <table><thead><tr><th>选择</th><th>模块</th><th>名称</th><th>类型</th><th>正文摘要</th><th>问题</th></tr></thead>
          <tbody>{groupedVisibleRequirements.flatMap(([module, requirements]) => [
            <tr className="requirement-module-group" key={`module-${module}`}><th colSpan={6}>模块：{module}</th></tr>,
            ...requirements.map((item) => {
            const atomic = atomicByRequirementId.get(item.requirement_id);
            const relatedCriteria = (analysis.acceptance_criteria ?? []).filter((criterion) => criterion.requirement_id === item.requirement_id);
            const relatedFindings = (analysis.findings ?? []).filter((finding) => item.source_references.some(
              (source) => finding.source_reference?.reference_id !== undefined
                && source.reference_id === finding.source_reference.reference_id));
            const relatedVisuals = (analysis.visual_inferences ?? []).filter((inference) => item.source_references.some(
              (source) => source.reference_id === inference.source_reference.reference_id));
            const relatedConflicts = (analysis.conflicts ?? []).filter((conflict) => conflict.affected_modules.includes(item.module));
            return <tr key={item.requirement_id}>
              <td><input aria-label={`选择 ${item.name}`} type="checkbox" disabled={analysis.status === "confirmed"}
                checked={selected.has(item.requirement_id)} onChange={() => refresh(updateRequirementSelection(
                  projectId, analysis.id, selected.has(item.requirement_id)
                    ? [...selected].filter((id) => id !== item.requirement_id) : [...selected, item.requirement_id],
                ))} /></td><td>{item.module}</td><td>{item.name}</td><td>{item.requirement_type}</td>
              <td>{item.statement}<details><summary>展开详情</summary><p>{item.analysis_note}</p>
                <p>来源：{item.source_references.map((source) => `${source.filename} ${source.locator}`).join("；")}</p>
                <p>验收条件：{relatedCriteria.map((criterion) => criterion.statement).join("；") || "未提供"}</p>
                <p>内部原子拆分：{atomic?.statement ?? "未提供"}</p>{atomic?.stable_requirement_id && <p>稳定需求 ID：{atomic.stable_requirement_id}</p>}
                {relatedFindings.map((finding) => <p key={finding.finding_id}>问题：{finding.summary}（{finding.status}）
                  {analysis.status === "draft" && finding.status === "pending_confirmation" && <button onClick={() => refresh(updateFinding(
                    projectId, analysis.id, finding.finding_id, "resolved"))}>标记已处理</button>}</p>)}
                {relatedVisuals.map((inference) => <p key={inference.inference_id}>视觉推断：{inference.description}（{inference.decision}）
                  {analysis.status === "draft" && inference.decision === "pending_confirmation" && <button onClick={() => refresh(updateVisualInference(
                    projectId, analysis.id, inference.inference_id, "rejected"))}>不作为需求事实</button>}</p>)}
                {relatedConflicts.map((conflict) => <p key={conflict.conflict_id}>冲突：{conflict.topic}（{conflict.decision}）
                  {analysis.status === "draft" && ["unresolved", "awaiting_external_confirmation"].includes(conflict.decision) && <button onClick={() => refresh(decideRequirementConflict(
                    projectId, analysis.id, conflict.conflict_id, "srs_preferred", confirmerName))}>以 SRS 为准</button>}</p>)}
              </details></td><td>{rowHasProblem(item) ? "有阻塞问题" : "无"}</td>
            </tr>;
          })])}</tbody>
        </table>
        {unassignedFindings.length > 0 && <section className="suggestion-card" aria-label="需人工处理的全局发现">
          <h4>需人工处理的全局发现</h4>
          {unassignedFindings.map((finding) => <p key={finding.finding_id}>
            问题：{finding.summary}（{finding.status}）
            {analysis.status === "draft" && finding.status === "pending_confirmation" && <button onClick={() => refresh(updateFinding(
              projectId, analysis.id, finding.finding_id, "resolved"))}>标记已处理</button>}
          </p>)}
        </section>}
      </div>
      {analysis.status === "draft" && <form className="project-form" onSubmit={(event) => {
        event.preventDefault(); refresh(confirmRequirementReview(projectId, analysis.id, confirmerName));
      }}><label>确认人名称<input value={confirmerName} onChange={(event) => setConfirmerName(event.target.value)} /></label>
        <button type="submit" disabled={!selected.size || blockedCount > 0}>确认已选需求</button></form>}
    </>}
  </section>;
}

const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
