import { useEffect, useState } from "react";

import { getRunPreflight } from "./v020_api";
import type { RunEvidence, RunMode, RunPage, RunPreflight } from "./v020_types";

const modeLabels: Record<RunMode, string> = {
  direct: "真实模型（直接调用）",
  skill: "真实模型（Skill 工作流）",
  local: "本地模式（不调用 AI）",
};

export function WorkflowRunControls({ projectId, page, actionLabel, latestRun, roles = [], disabled = false,
  supplementalRequirements = "", templateMode = "default", templateMappingId = null, beforeAction, onRun,
  onRunSettled, allowedModes = ["direct", "skill", "local"], defaultMode = "local",
  preflightActionLabel = "查看调用范围" }: {
  projectId: number; page: RunPage; actionLabel: string; latestRun?: RunEvidence; roles?: string[]; disabled?: boolean;
  supplementalRequirements?: string; templateMode?: "default" | "uploaded"; templateMappingId?: number | null;
  allowedModes?: RunMode[]; defaultMode?: RunMode;
  preflightActionLabel?: string;
  beforeAction?: React.ReactNode;
  onRun: (mode: RunMode, confirmed: boolean) => Promise<{ reused?: boolean } | void>;
  onRunSettled?: () => Promise<void>;
}) {
  const [mode, setMode] = useState<RunMode>(allowedModes.includes(defaultMode) ? defaultMode : allowedModes[0]);
  const [preflight, setPreflight] = useState<RunPreflight | null>(null);
  const [busy, setBusy] = useState(false);
  const [runningSince, setRunningSince] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState("");
  const [reuseNotice, setReuseNotice] = useState(false);
  useEffect(() => {
    if (runningSince === null) return;
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - runningSince) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [runningSince]);

  const executeRun = async () => {
    let runError: unknown;
    try { return await onRun(mode, true); }
    catch (reason) { runError = reason; throw reason; }
    finally {
      try { await onRunSettled?.(); }
      catch (refreshError) { if (runError === undefined) throw refreshError; }
    }
  };

  const prepare = async () => {
    setBusy(true); setError(""); setPreflight(null); setReuseNotice(false);
    try {
      const result = await getRunPreflight(projectId, page, mode, roles, {
        templateMode, templateMappingId, supplementalRequirements,
      });
      if (mode === "local") { setElapsedSeconds(0); setRunningSince(Date.now());
        const result = await executeRun(); setReuseNotice(Boolean(result?.reused)); }
      else setPreflight(result);
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); if (mode === "local") setRunningSince(null); }
  };
  const confirm = async () => {
    setBusy(true); setError(""); setReuseNotice(false);
    try { setElapsedSeconds(0); setRunningSince(Date.now());
      const result = await executeRun(); setReuseNotice(Boolean(result?.reused)); }
    catch (reason) { setError(message(reason)); }
    finally { setBusy(false); setRunningSince(null); setPreflight(null); }
  };

  const prepareLabel = mode === "local" ? actionLabel : preflightActionLabel;

  return <section className="run-controls" aria-label={`${actionLabel}运行设置`}>
    {allowedModes.length === 1
      ? <p><strong>运行方式：</strong>{modeLabels[mode]}</p>
      : <fieldset className="mode-picker"><legend>运行方式</legend>
        {allowedModes.map((value) => <label key={value}>
          <input type="radio" name={`mode-${page}`} value={value} checked={mode === value}
            onChange={() => { setMode(value); setPreflight(null); }} /> {modeLabels[value]}
        </label>)}
      </fieldset>}
    {beforeAction}
    <div className="action-row"><button type="button" disabled={busy || disabled} onClick={() => void prepare()}>
      {busy ? "正在准备…" : prepareLabel}
    </button></div>
    {preflight && <section className="run-confirmation" aria-label="真实模型调用确认">
      <h4>调用前确认（尚未发送）</h4>
      <p>请确认模型、输入范围和 Token 预算；点击下方确认按钮后才会发送给模型。</p>
      <dl><dt>模型</dt><dd>{preflight.provider} · {preflight.model}（{preflight.verification_status}）</dd>
        <dt>输入范围</dt><dd>{inputSummary(preflight)}</dd>
        <dt>人工补充</dt><dd>{preflight.supplemental_notes || "无"}</dd>
        {preflight.template_filename && <><dt>测试用例模板</dt><dd>{preflight.template_filename}</dd></>}
        {page === "cases" && <><dt>补充生成要求</dt><dd>{preflight.supplemental_requirements || "无"}</dd></>}
        <dt>Prompt / Skill</dt><dd>{preflight.prompt_version}{preflight.skill_version ? ` · ${preflight.skill_version}` : ""}</dd>
        <dt>预计 Token</dt><dd>输入约 {preflight.estimated_input_tokens.toLocaleString()}；最大输出 {preflight.max_output_tokens.toLocaleString()}</dd>
        {preflight.model_timeout_seconds && <><dt>模型响应超时</dt><dd>{preflight.model_timeout_seconds} 秒</dd></>}
        <dt>费用</dt><dd>{costText(preflight.estimated_cost)}</dd></dl>
      <div className="action-row"><button type="button" disabled={busy} onClick={() => void confirm()}>
        {actionLabel.startsWith("开始") ? `确认并${actionLabel}` : `确认并执行：${actionLabel}`}</button>
        <button type="button" className="secondary" onClick={() => setPreflight(null)}>取消</button></div>
    </section>}
    {runningSince !== null ? <section className="run-evidence running" aria-label="运行状态"><header><strong>运行状态：正在执行</strong><span>{modeLabels[mode]}</span></header>
      <p>当前阶段：准备输入 / 调用模型 · 已用时间：{elapsedSeconds} 秒</p><p>正在等待本次运行返回；预计剩余时间不可获得，不显示虚构倒计时。</p></section>
      : latestRun ? <RunEvidenceCard run={latestRun} /> : <section className="run-evidence pending" aria-label="运行状态"><header><strong>运行状态：尚未执行</strong></header>
        <p>{mode === "local" ? `选择运行方式后点击“${actionLabel}”。` : "先查看调用范围，确认后才会调用模型。"}</p></section>}
    {reuseNotice && <p className="notice"><strong>已复用已有结果：</strong>输入与配置未变化，未再次调用模型，也未新增结果。</p>}
    {error && latestRun?.status !== "failed" && <p role="alert" className="error">{error}</p>}
  </section>;
}

export function RunEvidenceCard({ run }: { run: RunEvidence }) {
  return <section className={`run-evidence ${run.status}`} aria-label="运行状态">
    <header><strong>运行状态：{statusLabel(run.status)}</strong><span>{run.source_label}</span></header>
    <p>当前阶段：{run.stage} · 耗时：{run.duration_ms === null ? "正在计时" : `${(run.duration_ms / 1000).toFixed(1)} 秒`}</p>
    <p>模型：{run.provider} · {run.model} · {run.credential_source}；Prompt：{run.prompt_version}{run.skill_version ? ` · Skill ${run.skill_version}` : ""}</p>
    <p>输入：{inputSummary({ input_summary: run.input_summary })}；预计输入 {run.estimated_input_tokens.toLocaleString()} Token</p>
    <p>人工补充：{run.supplemental_notes || "无"}{run.template_filename ? `；模板：${run.template_filename}` : ""}{run.supplemental_requirements ? `；生成要求：${run.supplemental_requirements}` : ""}</p>
    <p>实际用量：{usageText(run)}；实际费用：{run.actual_cost ? costText(run.actual_cost) : "运行结束后更新"}</p>
    {run.stage_events.length > 0 && <ol className="stage-events">{run.stage_events.map((event) =>
      <li key={`${event.stage}-${event.status}`}>{event.stage}：{event.detail}</li>)}</ol>}
    {run.error && <p className="error">失败原因：{run.error}</p>}
    <p><strong>下一步建议：</strong>{run.next_step}</p>
  </section>;
}

function inputSummary(value: Pick<RunPreflight, "input_summary">): string {
  const summary = value.input_summary;
  if (summary.context_chunk_count || summary.fragment_count) {
    const source = `${summary.file_count} 份资料、${summary.source_fragment_count ?? summary.fragment_count} 个来源片段，整理为 ${summary.context_chunk_count ?? summary.fragment_count} 个模型上下文块`;
    return summary.material_understanding_used ? `${source}；已使用 AI 阅读整理结果` : source;
  }
  return `${summary.analysis_row_count} 条分析结果、其中已选 ${summary.selected_row_count} 条${summary.roles.length ? `、角色 ${summary.roles.length} 个` : ""}`;
}
function costText(cost: { status: string; reason?: string; amount?: number; currency?: string }): string {
  return cost.status === "available" ? `${cost.amount ?? "-"} ${cost.currency ?? ""}` : `不可获得：${cost.reason ?? "未提供"}`;
}
function usageText(run: RunEvidence): string {
  const usage = run.actual_usage;
  if (!usage || usage.status === "unavailable") return `不可获得：${usage?.reason ?? "运行尚未完成"}`;
  return `输入 ${usage.input_tokens ?? "-"} / 输出 ${usage.output_tokens ?? "-"} / 合计 ${usage.total_tokens ?? "-"} Token`;
}
function statusLabel(status: RunEvidence["status"]): string {
  return ({ running: "正在执行", completed: "已完成", failed: "失败" })[status];
}
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
