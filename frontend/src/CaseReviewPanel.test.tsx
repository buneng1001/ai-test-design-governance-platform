import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { CaseReviewPanel } from "./CaseReviewPanel";
import { CaseReviewSuggestion } from "./api";

afterEach(() => vi.restoreAllMocks());

test("三个独立评审完成后可逐条处置并确认用例", async () => {
  const user = userEvent.setup();
  const roles: CaseReviewSuggestion["role"][] = ["product_manager", "test_manager", "project_manager"];
  let suggestions: CaseReviewSuggestion[] = ["s1", "s2", "s3"].map((id, index) => ({
    id, candidate_id: "candidate-1", role: roles[index],
    suggestion_type: "supplement", summary: "补充异常恢复场景的可观察预期", rationale: "保留角色理由",
    source_references: [], limitations: ["未读取其他评审员输出"], disposition: null,
  }));
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/reviews") && init?.method === "POST") {
      return new Response(JSON.stringify({ id: 1, generation_id: 1, status: "completed",
        reviewer_runs: [{ role: "product_manager", ai_run_id: 1 }, { role: "test_manager", ai_run_id: 2 },
          { role: "project_manager", ai_run_id: 3 }], suggestions, groups: [{ id: "g1",
          summary: "补充异常恢复场景的可观察预期",
          original_suggestion_ids: ["s1", "s2", "s3"],
          source_roles: ["product_manager", "test_manager", "project_manager"] }],
        revisions: [], inclusion: {}, confirmed_by: null }), { status: 201 });
    }
    if (url.includes("/suggestions/")) {
      suggestions = suggestions.map((item) => ({ ...item, disposition: "accepted" }));
      return new Response(JSON.stringify({ id: 1, generation_id: 1, status: "completed", reviewer_runs: [],
        suggestions, groups: [], revisions: [{ id: "r1", candidate_id: "candidate-1", revision: 1,
          stable_case_id: null }],
        inclusion: {}, confirmed_by: null }), { status: 200 });
    }
    if (url.includes("/status")) {
      return new Response(JSON.stringify({ id: 1, generation_id: 1, status: "confirmed", reviewer_runs: [],
        suggestions, groups: [], revisions: [{ id: "r1", candidate_id: "candidate-1", revision: 1,
          stable_case_id: "case-1", lifecycle_status: "closed", participation_status: "not_included" }],
        inclusion: { "candidate-1": true }, confirmed_by: "测试工程师" }), { status: 200 });
    }
    return new Response(JSON.stringify({ id: 1, generation_id: 1, status: "confirmed", reviewer_runs: [],
      suggestions: suggestions.map((item) => ({ ...item, disposition: "accepted" })), groups: [],
      revisions: [{ id: "r1", candidate_id: "candidate-1", revision: 1, stable_case_id: "case-1",
        lifecycle_status: "effective", participation_status: "included" }],
      inclusion: { "candidate-1": true }, confirmed_by: "测试工程师" }), { status: 200 });
  });

  render(<CaseReviewPanel projectId={1} generationId={1} candidateIds={["candidate-1"]} />);
  await user.click(screen.getByRole("button", { name: "开始三角色 AI 评审" }));
  expect(await screen.findByText(/独立 AI 运行：3 个/)).toBeInTheDocument();
  expect(screen.getByText(/归并来源：产品经理评审员、测试经理评审员、项目经理评审员/)).toBeInTheDocument();
  await user.click(screen.getAllByRole("button", { name: "采纳" })[0]);
  await user.click(screen.getByRole("button", { name: "完成用例确认" }));
  expect(await screen.findByText(/用例已确认/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "下载用例文件" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "变更用例状态" }));
  expect(await screen.findByText(/生命周期：closed/)).toBeInTheDocument();
});
