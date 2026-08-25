import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { TaskPublicationPanel } from "./TaskPublicationPanel";


test("测试工程师可以完成发布确认并看到版本化通用测试任务", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    contract_version: "test-task.v1",
    task_id: "task-demo",
    task_version: 1,
    project_id: 1,
    case_review_batch_id: 2,
    execution_scope: "selected",
    execution_target: "test_execution_diagnostics",
    cases: [{
      stable_case_id: "case-demo", case_revision_id: "revision-demo", case_revision: 1,
      title: "验证状态保存", priority: "P1", preconditions: ["设备已连接"], parameters: {}, steps: [],
      expected_result: "状态被保存", verdict_method: "expected_result_match", evidence_requirements: ["日志"],
    }],
    published_by: "测试工程师",
    published_at: "2026-08-25T00:00:00Z",
  }), { status: 201 }));

  render(<TaskPublicationPanel projectId={1} />);
  await user.type(screen.getByLabelText("评审批次 ID"), "2");
  await user.type(screen.getByLabelText("稳定用例 ID"), "case-demo");
  await user.selectOptions(screen.getByLabelText("执行目标"), "test_execution_diagnostics");
  await user.click(screen.getByRole("button", { name: "完成发布确认并生成任务" }));

  expect(await screen.findByRole("status")).toHaveTextContent("test-task.v1");
  expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/projects/1/case-review-batches/2/test-tasks",
    expect.objectContaining({ method: "POST" }),
  );
});
