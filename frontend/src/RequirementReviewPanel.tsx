import { useState } from "react";

import {
  confirmRequirementReview,
  createRequirementReview,
  listRequirementVersions,
  RequirementAnalysis,
  updateAtomicRequirement,
  updateFinding,
  updateVisualInference,
  decideRequirementConflict,
  updateRequirementSelection,
} from "./api";

export function RequirementReviewPanel({ projectId }: { projectId: number }) {
  const [analysis, setAnalysis] = useState<RequirementAnalysis | null>(null);
  const [version, setVersion] = useState(1);
  const [confirmerName, setConfirmerName] = useState("测试工程师");
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"mock" | "real">("mock");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [moduleFilter, setModuleFilter] = useState("");
  const [problemOnly, setProblemOnly] = useState(false);

  const runReview = async () => {
    try {
      const versions = await listRequirementVersions(projectId);
      if (versions.length === 0) throw new Error("请先发布需求版本");
      setAnalysis(await createRequirementReview(projectId, version, mode));
      setError("");
    } catch (reason) {
      setError(message(reason));
    }
  };

  const refresh = (request: Promise<RequirementAnalysis>) => {
    void request.then(setAnalysis).then(() => setError("")).catch((reason: unknown) => {
      setError(message(reason));
    });
  };

  const problemIds = new Set((analysis?.findings ?? []).flatMap((finding) =>
    (analysis?.requirements ?? []).filter((item) => item.source_references.some((source) =>
      source.reference_id === finding.source_reference?.reference_id,
    )).map((item) => item.requirement_id),
  ));
  const requirements = (analysis?.requirements ?? []).filter((item) =>
    (!search || `${item.name} ${item.statement} ${item.module}`.includes(search))
    && (!moduleFilter || item.module === moduleFilter)
    && (!problemOnly || problemIds.has(item.requirement_id)),
  );
  const modules = [...new Set((analysis?.requirements ?? []).map((item) => item.module))];
  const problemRequirementIds = problemIds;
  const pageItems = requirements.slice((page - 1) * 20, page * 20);
  const selected = new Set(analysis?.selected_requirement_ids ?? requirements.map((item) => item.requirement_id));
  const conflicts = analysis?.conflicts ?? [];
  const testItems = analysis?.test_items ?? [];
  const acceptanceCriteria = analysis?.acceptance_criteria ?? [];

  return (
    <section className="panel">
      <h2>需求评审与确认</h2>
      {!analysis && <>
        <label>需求版本
          <input type="number" min="1" value={version} onChange={(event) => setVersion(Number(event.target.value))} />
        </label>
        <label>分析方式<select value={mode} onChange={(event) => setMode(event.target.value as "mock" | "real")}>
          <option value="mock">Mock AI（离线）</option><option value="real">真实模型</option>
        </select></label>
        <button onClick={() => void runReview()}>运行原子需求与需求评审</button>
      </>}
      {error && <p role="alert" className="error">{error}</p>}
      {analysis && <>
        <p>状态：{analysis.status === "confirmed" ? "需求已确认" : "等待测试工程师处理"} · 已生成语义分析结果 ·
          {analysis.is_mock ? " Mock AI" : " 真实模型"}</p>
        <div className="requirement-summary">
          <h3>按模块归并的需求表</h3>
          {requirements.length === 0 && <p className="muted">模型没有返回需求候选，请检查输入或模型输出。</p>}
          <label>搜索需求<input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></label>
          <label>模块筛选<select value={moduleFilter} onChange={(event) => { setModuleFilter(event.target.value); setPage(1); }}>
            <option value="">全部模块</option>{modules.map((module) => <option key={module} value={module}>{module}</option>)}
          </select></label>
          <label><input type="checkbox" checked={problemOnly} onChange={(event) => setProblemOnly(event.target.checked)} /> 仅显示有问题标记</label>
          <button onClick={() => refresh(updateRequirementSelection(projectId, analysis.id, []))}>批量取消当前选择</button>
          <button onClick={() => refresh(updateRequirementSelection(projectId, analysis.id, requirements.map((item) => item.requirement_id)))}>全选筛选结果</button>
          {groupByModule(pageItems).map(([module, moduleRequirements]) => <article key={module}>
            <strong>{module}</strong>
            <table><thead><tr><th>名称</th><th>类型</th><th>需求</th><th>来源</th></tr></thead>
              <tbody>{moduleRequirements.map((item) => <tr key={item.requirement_id}>
                <td><input type="checkbox" checked={selected.has(item.requirement_id)} onChange={() => refresh(updateRequirementSelection(
                  projectId, analysis.id, selected.has(item.requirement_id)
                    ? [...selected].filter((id) => id !== item.requirement_id)
                    : [...selected, item.requirement_id],
                ))} /> {item.name}</td><td>{item.requirement_type}</td><td>{item.statement}<br />
                  <small>{item.analysis_note}</small><br />
                  <small>{problemRequirementIds.has(item.requirement_id) ? "问题标记：有待处理发现" : "问题标记：无"}</small></td>
                <td>{item.source_references.map((source) => `${source.filename} ${source.locator}`).join("；")}</td>
              </tr>)}</tbody>
            </table>
          </article>)}
          {requirements.length > 20 && <nav aria-label="需求分页"><button disabled={page === 1} onClick={() => setPage(page - 1)}>上一页</button>
            <span>第 {page} / {Math.ceil(requirements.length / 20)} 页</span>
            <button disabled={page >= Math.ceil(requirements.length / 20)} onClick={() => setPage(page + 1)}>下一页</button></nav>}
          <p>测试项：{testItems.length} · 验收条件：{acceptanceCriteria.length}</p>
          <h3>需求冲突表</h3>
          {conflicts.length === 0 && <p className="muted">未发现跨资料冲突。</p>}
          {conflicts.map((conflict) => <article key={conflict.conflict_id}>
            <strong>{conflict.topic}</strong><p>影响模块：{conflict.affected_modules.join("、")} ·
              影响测试项：{conflict.affected_test_items.join("、") || "无"} · 状态：{conflict.decision}</p>
            <p>处理人：{conflict.decided_by ?? "未处理"} · 处理说明：{conflict.decision_note ?? "无"}</p>
            <p>SRS：{conflict.srs_text}（{conflict.srs_source.filename} {conflict.srs_source.locator}）</p>
            <p>实现规格：{conflict.implementation_text}（{conflict.implementation_source.filename} {conflict.implementation_source.locator}）</p>
            {analysis.status === "draft" && <select value={conflict.decision} onChange={(event) => refresh(decideRequirementConflict(
              projectId, analysis.id, conflict.conflict_id,
              event.target.value as typeof conflict.decision, confirmerName,
            ))}><option value="unresolved">未解决</option><option value="srs_preferred">以 SRS 为准</option>
              <option value="implementation_preferred">以实现规格为准</option><option value="both_retained">两者保留</option>
              <option value="awaiting_external_confirmation">待外部确认</option></select>}
          </article>)}
          <h3>原子需求候选</h3>
          {analysis.atomic_requirements.map((candidate) => <article key={candidate.candidate_id}>
            <span>{candidate.statement}</span>
            <small>来源：{candidate.source_reference.filename} {candidate.source_reference.locator}</small>
            {candidate.decision === "pending_confirmation" && <div>
              <button onClick={() => refresh(updateAtomicRequirement(
                projectId, analysis.id, candidate.candidate_id, { decision: "accepted" },
              ))}>接受并获得稳定需求 ID</button>
              <button onClick={() => refresh(updateAtomicRequirement(
                projectId, analysis.id, candidate.candidate_id, { decision: "rejected" },
              ))}>拒绝</button>
            </div>}
            {candidate.stable_requirement_id && <small>稳定需求 ID：{candidate.stable_requirement_id}</small>}
          </article>)}
          <h3>需求评审发现</h3>
          {analysis.findings.map((finding) => <article key={finding.finding_id}>
            <span>{finding.summary}（{finding.finding_type}）</span>
            <small>{finding.reason} {finding.source_reference?.locator}</small>
            {finding.status === "pending_confirmation" && <div>
              <button onClick={() => refresh(updateFinding(
                projectId, analysis.id, finding.finding_id, "resolved",
              ))}>标记已解决</button>
              <button onClick={() => refresh(updateFinding(
                projectId, analysis.id, finding.finding_id, "rejected",
              ))}>拒绝发现</button>
            </div>}
          </article>)}
          {analysis.visual_inferences.map((inference) => <article key={inference.inference_id}>
            <span>视觉推断（待人工确认）：{inference.description}</span>
            <small>来源：{inference.source_reference.locator}</small>
            {inference.decision === "pending_confirmation" && <div>
              <button onClick={() => refresh(updateVisualInference(
                projectId, analysis.id, inference.inference_id, "accepted",
              ))}>
                接受为需求事实
              </button>
              <button onClick={() => refresh(updateVisualInference(
                projectId, analysis.id, inference.inference_id, "rejected",
              ))}>拒绝</button>
            </div>}
          </article>)}
        </div>
        {analysis.status === "draft" && <form className="project-form" onSubmit={(event) => {
          event.preventDefault();
          refresh(confirmRequirementReview(projectId, analysis.id, confirmerName));
        }}>
          <label>确认人名称<input value={confirmerName} onChange={(event) => setConfirmerName(event.target.value)} /></label>
          <button type="submit">完成需求确认</button>
        </form>}
      </>}
    </section>
  );
}

const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";

const groupByModule = (requirements: RequirementAnalysis["requirements"]): Array<[
  string, RequirementAnalysis["requirements"]
]> => Object.entries(requirements.reduce<Record<string, RequirementAnalysis["requirements"]>>(
  (groups, requirement) => ({ ...groups, [requirement.module]: [...(groups[requirement.module] ?? []), requirement] }),
  {},
));
