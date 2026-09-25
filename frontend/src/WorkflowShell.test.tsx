import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { WorkflowShell } from "./WorkflowShell";

const initialWorkflow = {
  project_id: 1, current_step: "upload", progress: 0,
  tabs: [
    { id: "upload", label: "上传文档", stage_ids: ["S00"], status: "current", blocked_reason: null },
    { id: "preview", label: "结构预览", stage_ids: ["S01", "S02"], status: "locked", blocked_reason: "请先上传并发布至少一份可解析的需求资料。" },
    { id: "suggestions", label: "新增建议", stage_ids: ["S03", "S04", "S05", "S06"], status: "locked", blocked_reason: "请先确认结构预览中的需求，并至少选择一项进入分析范围。" },
    { id: "review", label: "审核", stage_ids: ["S07", "S08"], status: "locked", blocked_reason: "请先完成新增建议的处置，并建立测试设计草稿。" },
    { id: "cases", label: "测试用例", stage_ids: [], status: "locked", blocked_reason: "请先在审核页确认测试点和生成范围。" },
  ],
  blockers: [], next_action: { label: "上传并发布需求资料", target_tab: "upload" },
  asset_ids: { requirement_version_id: null, requirement_analysis_id: null, test_design_id: null,
    case_generation_id: null, case_review_batch_id: null }, invalidated_draft_ids: [],
} as const;

afterEach(() => vi.restoreAllMocks());

test("默认只呈现五页签，并显示持久化工作流给出的解锁原因", async () => {
  mockRequests(initialWorkflow);
  render(<WorkflowShell projectId={1} />);

  expect(await screen.findByText("下一步：上传并发布需求资料")).toBeInTheDocument();
  expect(screen.getAllByRole("tab")).toHaveLength(5);
  expect(screen.getByRole("tab", { name: "结构预览" })).toBeDisabled();
  expect(screen.getAllByText("请先上传并发布至少一份可解析的需求资料。")).toHaveLength(1);
  expect(screen.queryByText("资产来源记录")).not.toBeInTheDocument();
});

test("刷新恢复上游变更后的重新确认状态", async () => {
  mockRequests({ ...initialWorkflow, current_step: "suggestions", progress: 2,
    tabs: initialWorkflow.tabs.map((tab) => tab.id === "suggestions" ? {
      ...tab, status: "needs_reconfirmation", blocked_reason: "上游需求版本已更新；受影响的下游草稿需要重新确认，不能继续沿用。",
    } : tab),
    next_action: { label: "重新确认受影响的下游草稿", target_tab: "suggestions" },
    invalidated_draft_ids: [7],
  });
  render(<WorkflowShell projectId={1} />);

  expect(await screen.findByText("上游内容已更新；1 个下游草稿需要重新确认。")).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "新增建议" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("下一步操作：重新确认受影响的下游草稿")).toBeInTheDocument();
});

test("工作流查询失败时显示可理解错误", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("服务不可用", { status: 503 }));
  render(<WorkflowShell projectId={1} />);

  expect(await screen.findByRole("alert")).toHaveTextContent("服务不可用");
});

function mockRequests(workflow: object) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/workflow")) return new Response(JSON.stringify(workflow), { status: 200 });
    if (url.includes("/model-providers")) return new Response(JSON.stringify([]), { status: 200 });
    return new Response("null", { status: 200 });
  });
}
