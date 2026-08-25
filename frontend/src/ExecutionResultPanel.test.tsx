import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { ExecutionResultPanel } from "./ExecutionResultPanel";


test("测试工程师可以导入结果、处理冲突并确认批次结论", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify({
      batch_id: 3,
      records: [{ id: 1, batch_id: 3, source_type: "manual", source_record_id: "r1",
        stable_case_id: "case-1", case_revision_id: "revision-1", execution_sequence: 1,
        status: "passed", actual_result: "ok", reason: "", executor: "", evidence_references: [],
        match_status: "matched", retest_of_result_id: null }],
      unresolved_records: [], case_summaries: [], conflicts: [{ id: 9, result_ids: [1, 2],
        statuses: { manual: "passed", generic_automation: "execution_failed" }, status: "open",
        decision: null, rationale: null, confirmed_by: null }], conclusion: null,
    }), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: 9, batch_id: 3, result_ids: [1, 2],
      statuses: {}, status: "resolved", decision: "passed", rationale: "已核对", confirmed_by: "测试工程师" })))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      batch_id: 3, records: [], unresolved_records: [], case_summaries: [], conflicts: [], conclusion: null,
    })))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      batch_id: 3, records: [], unresolved_records: [], case_summaries: [], conflicts: [],
      conclusion: { conclusion: "passed", rationale: "已确认", confirmer_name: "测试工程师" },
    })));

  render(<ExecutionResultPanel projectId={1} />);
  await user.type(screen.getByLabelText("执行批次 ID"), "3");
  await user.click(screen.getByRole("button", { name: "导入结果" }));
  expect(await screen.findByRole("status")).toHaveTextContent("已导入 1 条结果");
  await user.click(screen.getByRole("button", { name: "记录决定并解决" }));
  await user.click(screen.getByRole("button", { name: "确认批次结论" }));
  expect(await screen.findByText("批次结论已确认：passed")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/projects/1/execution-batches/3/conclusion",
    expect.objectContaining({ method: "POST" }),
  );
});
