import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { TestPointReviewPanel } from "./TestPointReviewPanel";

const analysis = {
  id: 7, project_id: 1, requirement_version_id: 2, status: "confirmed", is_mock: true,
  atomic_requirements: [], findings: [], visual_inferences: [], requirements: [], conflicts: [],
  selected_requirement_ids: [], test_items: [], acceptance_criteria: [], suggestions: [],
  supplemental_requirement_candidates: [], analysis_batches: [], ai_run_id: 1, confirmed_by: "测试工程师",
  test_point_review: {
    review_id: "test-point-review-7", status: "draft", modules: ["状态"],
    test_items: [{ test_item_id: "item-1", name: "状态保存", module: "状态", stable_requirement_ids: ["REQ-1"],
      source_references: [{ filename: "SRS.md", locator: "L1", reference_id: "ref-1" }] }],
    test_points: [{ skill_test_point_id: "S07-TP-001", platform_test_point_id: "point-1", test_item_id: "item-1",
      stable_requirement_ids: ["REQ-1"], rule_ids: ["AC-1"], direction: "boundary", objective: "验证状态保存的边界条件",
      source_references: [{ filename: "SRS.md", locator: "L1", reference_id: "ref-1" }] }],
    coverage_check: { passed: true, total_confirmed_requirement_count: 1, covered_requirement_count: 1,
      uncovered_requirement_ids: [], isolated_test_point_ids: [], missing_test_item_ids: [], direction_gaps: {} },
    selected_test_item_ids: [], selected_test_point_ids: [], handoff_version: null, confirmed_by: null, confirmed_at: null,
  },
} as const;

afterEach(() => vi.restoreAllMocks());

test("显示层级、默认折叠设计依据，并保存测试项范围", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if (String(input).endsWith("/test-point-review/selection")) {
      expect(init?.body).toBe(JSON.stringify({ test_item_ids: ["item-1"], test_point_ids: [] }));
      return new Response(JSON.stringify({ ...analysis, test_point_review: {
        ...analysis.test_point_review, selected_test_item_ids: ["item-1"],
      } }), { status: 200 });
    }
    return new Response(JSON.stringify(analysis), { status: 200 });
  });
  render(<TestPointReviewPanel projectId={1} analysisId={7} onWorkflowChanged={() => undefined} />);

  expect(await screen.findByText("需求模块 1 个；测试项 1 个；测试点 1 个；预计用例 0 条。")).toBeInTheDocument();
  expect(screen.getByText("专家设计依据与追溯").closest("details")).not.toHaveAttribute("open");
  await user.click(screen.getByLabelText("选择测试项：状态保存（状态）"));
  await user.click(screen.getByRole("button", { name: "保存生成范围" }));
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/test-point-review/selection"), expect.any(Object));
});
