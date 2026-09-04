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
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 42, version: 1, name: "当前任务" }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(analysis), { status: 200 }))
    .mockResolvedValue(new Response(JSON.stringify({ ...analysis, status: "confirmed" }), { status: 200 }));

  render(<RequirementReviewPanel projectId={1} />);
  expect(await screen.findByRole("option", { name: "V1 · 当前任务" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "运行原子需求与需求评审" }));
  expect(fetchMock.mock.calls[1]?.[0]).toContain("/requirement-versions/42/requirement-review");
  expect(fetchMock.mock.calls[1]?.[1]?.headers).toMatchObject({ "Content-Type": "application/json" });
  expect(await screen.findByText("设备必须保存状态。", { exact: false })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "接受并获得稳定需求 ID" }));
  await user.click(screen.getByRole("button", { name: "标记已解决" }));
  await user.click(screen.getByRole("button", { name: "接受为需求事实" }));
  await user.click(screen.getByRole("button", { name: "完成需求确认" }));
  expect(await screen.findByText((_, element) =>
    element?.tagName === "P" && (element.textContent?.includes("需求已确认") ?? false)
  )).toBeInTheDocument();
});

test("模型输出校验失败时不应误提示项目字段填写不正确", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 42, version: 1, name: "当前任务" }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: ["模型输出缺少必填字段"] }), { status: 422 }));

  render(<RequirementReviewPanel projectId={1} />);
  await user.click(await screen.findByRole("button", { name: "运行原子需求与需求评审" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "AI 分析结果格式不符合要求（不是项目字段错误），请确认需求资料已解析成功后重试；若仍失败，请切换分析方式",
  );
  expect(screen.queryByText("项目字段填写不正确")).not.toBeInTheDocument();
});
