import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { CaseGenerationPanel } from "./CaseGenerationPanel";

afterEach(() => vi.restoreAllMocks());

test("测试工程师可以生成并查看带追踪关系和设计依据的候选用例", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    id: 1, ai_run_id: 2, ai_run_status: "succeeded", is_mock: true, status: "succeeded",
    template_diagnostics: [], candidates: [{
      id: "candidate-1", candidate_key: "candidate-key-1", title: "保存状态 - 边界值", objective: "验证保存状态", variant: "boundary",
      preconditions: ["设备已连接"], steps: [{ order: 1, action: "输入", input: "边界值", expected: "保存成功" }],
      overall_expectation: "状态保持一致", evidence_requirements: ["截图"], requirement_ids: ["req-1"],
      requirement_references: [{ locator: "L1" }], scope_item_id: "scope-1", risk_item_id: "risk-scope-1",
      priority: "P1", case_sheet_name: "CSV", automation_mapping: "automation-scope-1",
      unexpressed_fields: [], design_basis: [{ method: "boundary", reason: "边界独立执行" }],
      pending_confirmations: ["最大值阈值待确认"],
    }],
  }), { status: 201 }));

  render(<CaseGenerationPanel projectId={1} />);
  await user.click(screen.getByRole("button", { name: "生成候选测试用例" }));

  expect(await screen.findByText("保存状态 - 边界值")).toBeInTheDocument();
  expect(screen.getByText(/追踪：需求/)).toHaveTextContent("需求 req-1；范围 scope-1； 风险 risk-scope-1；P1");
  expect(screen.getByText(/设计依据：边界独立执行/)).toBeInTheDocument();
  expect(screen.getByText(/待确认：最大值阈值待确认/)).toBeInTheDocument();
});

test("测试工程师保存候选编辑时调用持久化 API", async () => {
  const user = userEvent.setup();
  const candidate = {
    id: "candidate-1", candidate_key: "candidate-key-1", title: "保存状态 - 正常路径", objective: "验证保存状态", variant: "normal",
    preconditions: ["设备已连接"], steps: [{ order: 1, action: "输入", input: "正常值", expected: "保存成功" }],
    overall_expectation: "状态保持一致", evidence_requirements: ["截图"], requirement_ids: ["req-1"],
    requirement_references: [{ locator: "L1" }], scope_item_id: "scope-1", risk_item_id: "risk-scope-1",
    priority: "P1", case_sheet_name: "CSV", automation_mapping: "automation-scope-1",
    unexpressed_fields: [], design_basis: [{ method: "scenario", reason: "正常路径" }], pending_confirmations: [],
  };
  const generation = {
    id: 1, ai_run_id: 2, ai_run_status: "succeeded", is_mock: true, status: "succeeded",
    template_diagnostics: [], candidates: [candidate], removed_candidate_ids: [],
  };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if (String(input).includes("/candidates/")) {
      return new Response(JSON.stringify({ ...generation, candidates: [{ ...candidate, title: "人工编辑标题" }] }), { status: 200 });
    }
    return new Response(JSON.stringify(generation), { status: 201 });
  });

  render(<CaseGenerationPanel projectId={1} />);
  await user.click(screen.getByRole("button", { name: "生成候选测试用例" }));
  await user.clear(await screen.findByLabelText("标题-candidate-1"));
  await user.type(screen.getByLabelText("标题-candidate-1"), "人工编辑标题");
  await user.click(screen.getByRole("button", { name: "保存候选编辑" }));

  const request = fetchMock.mock.calls.find(([url]) => String(url).includes("/candidates/candidate-1"));
  expect(request).toBeDefined();
  expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ title: "人工编辑标题", reason: "生成预览中的人工修改" });
});
