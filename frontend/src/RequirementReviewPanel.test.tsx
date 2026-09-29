import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { RequirementReviewPanel } from "./RequirementReviewPanel";

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

const runControl = {
  id: "requirement-run-1", project_id: 1, workflow: "requirement_analysis", input_fingerprint: "v1:test",
  status: "running", next_batch: 1, batch_total: 1, completed_count: 0, final_asset_type: null, final_asset_id: null,
} as const;

const analysis = {
  id: 1, requirement_version_id: 42, status: "draft", is_mock: true,
  analysis_batches: [{ batch_number: 1, source_reference_ids: ["source-1"], status: "completed", ai_run_id: 8 }],
  requirements: [{
    requirement_id: "requirement-1", name: "保存状态", statement: "设备必须保存状态。",
    requirement_type: "functional", module: "状态管理", analysis_status: "ready",
    source_references: [{ reference_id: "source-1", filename: "requirements.md", locator: "lines:1-1" }],
    analysis_note: "状态变化应可追溯。",
  }],
  selected_requirement_ids: ["requirement-1"], conflicts: [], test_items: [],
  acceptance_criteria: [{ criterion_id: "criterion-1", requirement_id: "requirement-1", statement: "状态会被保存" }],
  atomic_requirements: [{ candidate_id: "requirement-1", stable_requirement_id: null, statement: "设备必须保存状态。", source_reference: { locator: "lines:1-1", filename: "requirements.md" }, decision: "pending_confirmation" }],
  findings: [], visual_inferences: [], confirmed_by: null,
};

test("结构预览只使用一张需求确认表，并在展开详情中展示验收条件和来源", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 42, version: 1, name: "当前任务" }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(runControl), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 200 }));

  render(<RequirementReviewPanel projectId={1} />);
  await user.click(await screen.findByRole("button", { name: "创建结构分析运行" }));
  await user.click(await screen.findByRole("button", { name: "执行下一批" }));

  expect(await screen.findByText("需求确认表")).toBeInTheDocument();
  expect(screen.getAllByRole("table")).toHaveLength(1);
  expect(screen.getByText("模块：状态管理")).toBeInTheDocument();
  expect(screen.queryByText("原子需求候选")).not.toBeInTheDocument();
  expect(screen.getByText("已选 1 · 未选 0 · 阻塞问题 0")).toBeInTheDocument();
  await user.click(screen.getByText("展开详情"));
  expect(screen.getByText("验收条件：状态会被保存")).toBeInTheDocument();
  expect(screen.getByText("来源：requirements.md lines:1-1")).toBeInTheDocument();
});

test("取消当前筛选结果只提交筛选后的选择集合", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 42, version: 1, name: "当前任务" }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(runControl), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...analysis, selected_requirement_ids: [] }), { status: 200 }));

  render(<RequirementReviewPanel projectId={1} />);
  await user.click(await screen.findByRole("button", { name: "创建结构分析运行" }));
  await user.click(await screen.findByRole("button", { name: "执行下一批" }));
  await user.click(await screen.findByRole("button", { name: "取消当前筛选结果" }));

  expect(fetchMock.mock.calls[3]?.[0]).toContain("/requirement-reviews/1/selection");
  expect(fetchMock.mock.calls[3]?.[1]?.body).toBe(JSON.stringify({ selected_requirement_ids: [] }));
});

test("全局评审发现可在确认表中处置，不会永久阻塞已选需求", async () => {
  const user = userEvent.setup();
  const withGlobalFinding = { ...analysis, findings: [{
    finding_id: "finding-global", finding_type: "ambiguity", summary: "缺少状态失效条件",
    reason: "材料没有说明状态何时失效", source_reference: null, status: "pending_confirmation",
  }] };
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 42, version: 1, name: "当前任务" }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(runControl), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(withGlobalFinding), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...withGlobalFinding, findings: [{
      ...withGlobalFinding.findings[0], status: "resolved",
    }] }), { status: 200 }));

  render(<RequirementReviewPanel projectId={1} />);
  await user.click(await screen.findByRole("button", { name: "创建结构分析运行" }));
  await user.click(await screen.findByRole("button", { name: "执行下一批" }));
  expect(await screen.findByText("需人工处理的全局发现")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "标记已处理" }));

  expect(fetchMock.mock.calls[3]?.[0]).toContain("/requirement-reviews/1/findings/finding-global");
  expect(await screen.findByText((_, element) => element?.textContent === "问题：缺少状态失效条件（resolved）")).toBeInTheDocument();
});

test("停止后的继续会先恢复持久化运行，再显式推进一个批次", async () => {
  const user = userEvent.setup();
  const stopped = { ...runControl, status: "stopped" };
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 42, version: 1, name: "当前任务" }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(runControl), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(stopped), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 200 }));

  render(<RequirementReviewPanel projectId={1} />);
  await user.click(await screen.findByRole("button", { name: "创建结构分析运行" }));
  await user.click(screen.getByRole("button", { name: "停止运行" }));
  await user.click(await screen.findByRole("button", { name: "继续运行" }));

  expect(fetchMock.mock.calls[3]?.[0]).toContain("/requirement-review-runs/requirement-run-1/resume");
  expect(await screen.findByText("需求确认表")).toBeInTheDocument();
});
