import { useEffect, useState } from "react";

import { getProjectWorkflow, ProjectWorkflowView } from "./api";
import { ModelConfigPanel } from "./ModelConfigPanel";

const pageDescriptions: Record<ProjectWorkflowView["tabs"][number]["id"], string> = {
  upload: "上传当前任务需要的需求资料，并查看文件解析状态与诊断。",
  preview: "查看已解析资料的结构，并确认进入后续流程的需求。",
  suggestions: "处理基于已确认需求产生的新增建议，保留人工处置边界。",
  review: "审核测试点、覆盖与生成范围；本页不提前生成详细测试步骤。",
  cases: "根据已确认范围生成、评审和管理可追溯的测试用例。",
};

export function WorkflowShell({ projectId }: { projectId: number }) {
  const [workflow, setWorkflow] = useState<ProjectWorkflowView | null>(null);
  const [activeTab, setActiveTab] = useState<ProjectWorkflowView["tabs"][number]["id"]>("upload");
  const [error, setError] = useState("");

  useEffect(() => {
    void getProjectWorkflow(projectId).then((view) => {
      if (!Array.isArray(view.tabs) || view.tabs.length !== 5) {
        throw new Error("工作流状态格式不完整，请刷新后重试");
      }
      setWorkflow(view);
      setActiveTab(view.current_step);
      setError("");
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "工作流状态加载失败"));
  }, [projectId]);

  if (!workflow) return error
    ? <p role="alert" className="error">{error}</p>
    : <p className="muted">正在恢复项目工作流…</p>;
  const active = workflow.tabs.find((tab) => tab.id === activeTab) ?? workflow.tabs[0];
  return <div className="workflow-layout">
    <aside className="workflow-sidebar" aria-label="工作流与模型设置">
      <section className="workflow-summary">
        <h2>当前任务</h2>
        <p>进度：{workflow.progress} / 5</p>
        <p>下一步：{workflow.next_action.label}</p>
        {workflow.invalidated_draft_ids.length > 0 && <p className="error">上游内容已更新；{workflow.invalidated_draft_ids.length} 个下游草稿需要重新确认。</p>}
      </section>
      <nav aria-label="主流程步骤">
        <ol className="workflow-steps">
          {workflow.tabs.map((tab, index) => <li key={tab.id}>
            <button type="button" className={`workflow-step ${tab.status}`} disabled={tab.status === "locked"}
              aria-current={tab.id === active.id ? "step" : undefined} onClick={() => setActiveTab(tab.id)}>
              <span>{index + 1}. {tab.label}</span><small>{statusLabel(tab.status)}</small>
            </button>
            {tab.blocked_reason && <p className="workflow-blocker">{tab.blocked_reason}</p>}
          </li>)}
        </ol>
      </nav>
      <section className="workflow-summary" aria-label="运行摘要">
        <h2>运行摘要</h2>
        <p>需求版本：{workflow.asset_ids.requirement_version_id ?? "尚未建立"}</p>
        <p>测试设计：{workflow.asset_ids.test_design_id ?? "尚未建立"}</p>
      </section>
      <ModelConfigPanel />
    </aside>
    <section className="workflow-main" aria-label="五页签主流程">
      <div className="workflow-tabs" role="tablist" aria-label="主流程页签">
        {workflow.tabs.map((tab) => <button key={tab.id} type="button" role="tab" disabled={tab.status === "locked"}
          aria-selected={tab.id === active.id} className={`workflow-tab ${tab.status}`}
          onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
      </div>
      <article className="panel workflow-panel" role="tabpanel">
        <p className="eyebrow">第 {workflow.tabs.findIndex((tab) => tab.id === active.id) + 1} 步
          {active.stage_ids.length > 0 ? ` · ${active.stage_ids.join("–")}` : ""}</p>
        <h2>{active.label}</h2>
        <p>{pageDescriptions[active.id]}</p>
        <p className="workflow-action">下一步操作：{workflow.next_action.target_tab === active.id
          ? workflow.next_action.label : "请按左侧步骤完成当前依赖。"}</p>
        {active.blocked_reason && <p role="status" className="error">{active.blocked_reason}</p>}
        <p className="muted">此页签保留为主流程入口；具体阶段命令继续使用各自明确的 API，避免一个万能更新接口。</p>
      </article>
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  </div>;
}

function statusLabel(status: ProjectWorkflowView["tabs"][number]["status"]): string {
  return ({ locked: "未解锁", current: "当前步骤", completed: "已完成",
    needs_reconfirmation: "需要重新确认" })[status];
}
