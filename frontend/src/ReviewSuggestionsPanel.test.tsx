import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ReviewSuggestionsPanel } from "./ReviewSuggestionsPanel";

afterEach(() => vi.restoreAllMocks());

const analysis = {
  id: 3, requirement_version_id: 1, status: "confirmed", is_mock: true, requirements: [], analysis_batches: [],
  selected_requirement_ids: ["requirement-1"], conflicts: [], test_items: [], acceptance_criteria: [], atomic_requirements: [],
  findings: [], visual_inferences: [], supplemental_requirement_candidates: [], confirmed_by: "测试工程师",
  suggestions: [
    ["normal", "material_explicit"], ["exception", "analysis_inference"], ["boundary", "analysis_inference"], ["risk", "awaiting_confirmation"],
  ].map(([direction, sourceType], index) => ({
    suggestion_id: `suggestion-${index}`, direction, problem_type: "omission", statement: `建议 ${index}`,
    source_type: sourceType, source_references: [{ reference_id: "ref-1", filename: "requirements.md", locator: "lines:1-1" }],
    related_requirement_ids: ["requirement-1"], impact_scope: "模块：状态", proposed_requirement_statement: null,
    disposition: "pending_confirmation",
  })),
};

test("新增建议页展示四个分析方向和来源，并提供四类人工处置", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/requirement-reviews/3")) return new Response(JSON.stringify(analysis), { status: 200 });
    if (url.includes("/suggestions/")) return new Response(JSON.stringify(analysis), { status: 200 });
    return new Response("null", { status: 200 });
  });

  render(<ReviewSuggestionsPanel projectId={1} analysisId={3} onWorkflowChanged={() => undefined} />);

  expect(await screen.findByText("正常场景 · omission")).toBeInTheDocument();
  expect(screen.getByText("异常场景 · omission")).toBeInTheDocument();
  expect(screen.getByText("边界条件 · omission")).toBeInTheDocument();
  expect(screen.getByText("隐性风险 · omission")).toBeInTheDocument();
  expect(screen.getByText(/来源类型：材料明示/)).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "采纳" })).toHaveLength(4);

  await user.click(screen.getAllByRole("button", { name: "采纳" })[0]);
  await user.click(screen.getAllByRole("button", { name: "拒绝" })[1]);
  await user.click(screen.getAllByRole("button", { name: "待外部确认" })[2]);
  await user.click(screen.getAllByRole("button", { name: "保存修改" })[3]);

  const bodies = fetchMock.mock.calls.slice(1).map((call) => String((call[1] as RequestInit).body));
  expect(bodies).toContain(JSON.stringify({ disposition: "accepted" }));
  expect(bodies).toContain(JSON.stringify({ disposition: "rejected" }));
  expect(bodies).toContain(JSON.stringify({ disposition: "awaiting_external_confirmation" }));
  expect(bodies).toContain(JSON.stringify({ disposition: "modified", statement: "建议 3" }));
});
