import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { ChangeImpactPanel } from "./ChangeImpactPanel";

const analysis = {
  id: 4, base_version_id: 1, target_version_id: 2, status: "pending_change_confirmation" as const,
  changes: [{ id: "change-1", change_type: "modified", summary: "状态规则已修改",
    base_source_reference: { locator: "L1" }, target_source_reference: { locator: "L1" },
    status: "pending_confirmation" as const }], impacts: [{ kind: "case", identifier: "CASE-1",
    title: "保存状态", reason: "需求变更" }], regression_candidates: [], ai_supplements: [],
};

test("测试工程师可以确认 V1→V2 变更并确认回归选择", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...analysis, status: "confirmed" }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: 8, analysis_id: 4, status: "pending_confirmation",
      candidates: [{ stable_case_id: "CASE-1", title: "保存状态", deterministic: true,
        reasons: ["requirement_change"], ai_supplement_reason: null, selected: null, decision_reason: null }] }),
      { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: 8, analysis_id: 4, status: "confirmed", candidates: [] }),
      { status: 200 }));

  render(<ChangeImpactPanel projectId={1} />);
  await user.type(screen.getByLabelText("V1 版本 ID"), "1");
  await user.type(screen.getByLabelText("V2 版本 ID"), "2");
  await user.click(screen.getByRole("button", { name: "分析需求变更" }));
  await user.click(await screen.findByRole("button", { name: "确认需求变更" }));
  await user.click(await screen.findByRole("button", { name: "生成回归候选" }));
  await user.click(await screen.findByRole("button", { name: "确认回归选择" }));
  expect(await screen.findByText("回归选择已由测试工程师确认。")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(4);
});
