import { runMaterialUnderstanding } from "./v020_api";
import type { WorkspaceState } from "./v020_types";
import { visibleRunForPage } from "./v020_run_state";
import { WorkflowRunControls } from "./WorkflowRunControls";

export function MaterialUnderstandingPanel({ projectId, workspace, onChanged }: {
  projectId: number; workspace: WorkspaceState; onChanged: () => Promise<void>;
}) {
  const latestRun = visibleRunForPage(workspace, "understanding");
  const understanding = workspace.material_understanding;

  return <section className="comparison-card material-understanding" aria-label="AI 资料理解">
    <header><div><p className="eyebrow">可选的分析前置步骤</p><h3>先让 AI 阅读并整理资料</h3></div></header>
    <p>模型会先通读当前资料，按来源整理摘要、关键事实、约束和待确认项。后续需求分析优先使用这份结果；资料与模型配置未变化时会直接复用，不重复调用模型。</p>
    <WorkflowRunControls projectId={projectId} page="understanding" actionLabel="AI 阅读并整理资料"
      latestRun={latestRun} disabled={!workspace.requirement_version} allowedModes={["direct"]} defaultMode="direct"
      preflightActionLabel="AI 阅读并整理资料（先确认范围）"
      onRunSettled={onChanged}
      onRun={async (_mode, confirmed, runId) => {
        return runMaterialUnderstanding(projectId, confirmed, runId);
      }} />
    {understanding && <section className="run-evidence completed" aria-label="AI 资料理解结果">
      <header><strong>资料理解结果</strong><span>{understanding.organized_fragments.length} 个上下文块</span></header>
      <p>{understanding.overview}</p>
      <div className="understanding-fragments">{understanding.organized_fragments.map((item) =>
        <details key={item.source_reference_id}><summary>{item.title} · {sourceLabel(item.source_reference)}</summary>
          <p>{item.summary}</p>
          <List label="关键事实" values={item.key_points} />
          <List label="约束" values={item.constraints} />
          <List label="待确认项" values={item.ambiguities} empty="无" />
        </details>)}</div>
    </section>}
  </section>;
}

function List({ label, values, empty = "未提取" }: { label: string; values: string[]; empty?: string }) {
  return <p><strong>{label}：</strong>{values.length ? values.join("；") : empty}</p>;
}

function sourceLabel(source: { filename?: string; locator?: string }): string {
  return [source.filename, source.locator].filter(Boolean).join(" · ") || "来源位置未标注";
}
