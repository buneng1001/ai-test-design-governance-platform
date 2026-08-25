import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { ExecutionBatchPanel } from "./ExecutionBatchPanel";


test("测试工程师可以选择范围、创建执行批次并下载人工执行文件", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify({
      id: 3, project_id: 1, test_task_id: "task-demo", test_task_version: 1,
      product_version: "1.0", requirement_version_id: 2, environment: "离线环境", scope: "冒烟",
      responsible_person: "测试工程师", execution_target: "manual", manual_file_format: "csv",
      cases: [{ stable_case_id: "case-demo", case_revision_id: "revision-demo", case_revision: 1,
        external_case_number: "TC-01", lifecycle_status: "effective", participation_status: "included",
        execution_sequence: 1, display_number: "TC-01-1", title: "验证状态" }],
      created_at: "2026-08-25T00:00:00Z",
    }), { status: 201 }))
    .mockResolvedValueOnce(new Response("execution_sequence,title\n1,验证状态\n", {
      status: 200, headers: { "content-disposition": 'attachment; filename="execution-batch-3.csv"' },
    }));

  render(<ExecutionBatchPanel projectId={1} />);
  await user.type(screen.getByLabelText("测试任务 ID"), "task-demo");
  await user.type(screen.getByLabelText("需求版本 ID"), "2");
  await user.type(screen.getByLabelText("选择稳定用例 ID（每行一个）"), "case-demo");
  await user.type(screen.getByLabelText("产品版本"), "1.0");
  await user.type(screen.getByLabelText("环境"), "离线环境");
  await user.type(screen.getByLabelText("测试范围"), "冒烟");
  await user.click(screen.getByRole("button", { name: "创建执行批次" }));
  expect(await screen.findByRole("status")).toHaveTextContent("已冻结 1 条用例");
  await user.click(screen.getByRole("button", { name: "下载人工执行文件" }));
  expect(fetchMock).toHaveBeenLastCalledWith("/api/projects/1/execution-batches/3/manual-file");
});
