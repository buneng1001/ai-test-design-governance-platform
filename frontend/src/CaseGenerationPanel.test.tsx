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
      id: "candidate-1", title: "保存状态 - 边界值", objective: "验证保存状态", variant: "boundary",
      preconditions: ["设备已连接"], steps: [{ order: 1, action: "输入", input: "边界值", expected: "保存成功" }],
      overall_expectation: "状态保持一致", evidence_requirements: ["截图"], requirement_ids: ["req-1"],
      requirement_references: [{ locator: "L1" }], scope_item_id: "scope-1", risk_item_id: "risk-scope-1",
      priority: "P1", case_sheet_name: "CSV", automation_mapping: "automation-scope-1",
      unexpressed_fields: [], design_basis: [{ method: "boundary", reason: "边界独立执行" }],
    }],
  }), { status: 201 }));

  render(<CaseGenerationPanel projectId={1} />);
  await user.click(screen.getByRole("button", { name: "生成候选测试用例" }));

  expect(await screen.findByText("保存状态 - 边界值")).toBeInTheDocument();
  expect(screen.getByText(/追踪：需求/)).toHaveTextContent("需求 req-1；范围 scope-1； 风险 risk-scope-1；P1");
  expect(screen.getByText(/设计依据：边界独立执行/)).toBeInTheDocument();
});
