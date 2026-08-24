import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { TemplateMappingPanel } from "./TemplateMappingPanel";

test("测试工程师可以上传并逐表确认模板映射", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify({
      id: 1, project_id: 1, version: 1, filename: "用例.csv", format: "csv", status: "draft",
      retained_sheet_names: ["CSV"], diagnostics: [], confirmed_by: null,
      sheets: [{
        name: "CSV", index: 0, role_suggestion: "case", role: "unknown", title_row_candidates: [1],
        title_row: 1, participates: false,
        columns: [{ index: 1, name: "用例标题", sample_values: [] }, { index: 2, name: "测试步骤", sample_values: [] },
          { index: 3, name: "预期结果", sample_values: [] }],
        field_mapping: { "用例标题": "title", "测试步骤": "steps", "预期结果": "overall_expectation" }, diagnostics: [],
      }],
    }), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ valid: true, diagnostics: [] }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      id: 1, project_id: 1, version: 1, filename: "用例.csv", format: "csv", status: "confirmed",
      retained_sheet_names: ["CSV"], diagnostics: [], confirmed_by: "测试工程师", sheets: [],
    }), { status: 200 }));

  render(<TemplateMappingPanel projectId={1} />);
  const file = new File(["用例标题,测试步骤,预期结果\n"], "用例.csv", { type: "text/csv" });
  await user.upload(screen.getByLabelText("上传 XLSX 或 CSV 用例模板"), file);
  expect(await screen.findByText(/用例.csv：发现 1 张工作表/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "确认模板映射" }));
  expect(await screen.findByText(/模板映射已确认/)).toBeInTheDocument();
});
