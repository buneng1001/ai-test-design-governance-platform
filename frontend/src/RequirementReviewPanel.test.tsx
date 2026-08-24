import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { RequirementReviewPanel } from "./RequirementReviewPanel";

const analysis = {
  id: 1,
  requirement_version_id: 1,
  status: "draft" as const,
  atomic_requirements: [{
    candidate_id: "candidate-1",
    stable_requirement_id: null,
    statement: "设备必须保存状态。",
    source_reference: { locator: "lines:1-1", filename: "requirements.md" },
    decision: "pending_confirmation" as const,
  }],
  findings: [{
    finding_id: "finding-1",
    finding_type: "missing_acceptance_criteria",
    summary: "需要明确验收标准",
    reason: "约束缺少可验证标准",
    status: "pending_confirmation",
    source_reference: { locator: "lines:1-1", filename: "requirements.md" },
  }],
  visual_inferences: [{
    inference_id: "visual-1",
    description: "页面存在状态徽标",
    source_reference: { locator: "image:1", filename: "screen.png" },
    decision: "pending_confirmation" as const,
  }],
  confirmed_by: null,
};

test("测试工程师可以处理原子需求、评审发现和视觉推断后完成需求确认", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 1, version: 1 }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 200 }))
    .mockResolvedValue(new Response(JSON.stringify({ ...analysis, status: "confirmed" }), { status: 200 }));

  render(<RequirementReviewPanel projectId={1} />);
  await user.click(screen.getByRole("button", { name: "运行原子需求与需求评审" }));
  expect(await screen.findByText("设备必须保存状态。", { exact: false })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "接受并获得稳定需求 ID" }));
  await user.click(screen.getByRole("button", { name: "标记已解决" }));
  await user.click(screen.getByRole("button", { name: "接受为需求事实" }));
  await user.click(screen.getByRole("button", { name: "完成需求确认" }));
  expect(await screen.findByText((_, element) =>
    element?.tagName === "P" && (element.textContent?.includes("需求已确认") ?? false)
  )).toBeInTheDocument();
});
