import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { AnalysisWorkspace } from "./AnalysisWorkspace";
import type { AnalysisRow, WorkspaceState } from "./v020_types";

afterEach(() => vi.restoreAllMocks());

test("需求分析大表只渲染当前页并按结果 ID 持久化跨页勾选", async () => {
  const user = userEvent.setup();
  const rows = Array.from({ length: 25 }, (_, index) => analysisRow(index + 1));
  const workspace: WorkspaceState = {
    project_id: 1, supplemental_notes: "", requirement_version: {} as WorkspaceState["requirement_version"],
    template: { mode: "default", mapping_id: null }, analysis_rows: rows, suggestions: [],
    review_suggestions: [], cases: [], case_generations: [], runs: [], exports: [],
  };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    selected_count: 1, affected_count: 1,
  }), { status: 200, headers: { "Content-Type": "application/json" } }));
  render(<AnalysisWorkspace projectId={1} workspace={workspace} onChanged={vi.fn(async () => undefined)} />);

  expect(screen.getAllByRole("checkbox")).toHaveLength(20);
  expect(screen.getByText("第 1 / 2 页")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getAllByRole("checkbox")).toHaveLength(5);
  await user.click(screen.getByLabelText("选择-测试点 21"));

  expect(fetchMock).toHaveBeenCalledWith("/api/v0.2/projects/1/analysis-selection", expect.objectContaining({
    method: "PATCH", body: JSON.stringify({ row_ids: ["row-21"], selected: true }),
  }));
  expect(within(screen.getByRole("region", { name: "需求分析筛选" })).getByRole("button", {
    name: "全选当前筛选结果（25）",
  })).toBeInTheDocument();
});

function analysisRow(index: number): AnalysisRow {
  return {
    id: `row-${index}`, project_id: 1, run_id: "run-1", module: `模块 ${Math.ceil(index / 5)}`,
    function_point: `功能点 ${index}`, test_item: `测试项 ${index}`, test_point: `测试点 ${index}`,
    source_reference_id: `input-${index}`, source: "requirements.md · 第1节", source_reference: {},
    ai_reason: "需求明确", information_gap: "", status: "ready", selected: false,
    origin: "analysis", mode: "local",
  };
}
