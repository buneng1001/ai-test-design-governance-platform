import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { WorkflowShell } from "./WorkflowShell";

const workspace = {
  project_id: 1, supplemental_notes: "关注异常提示", requirement_version: null,
  template: { mode: "default", mapping_id: null }, analysis_rows: [], suggestions: [],
  review_suggestions: [], cases: [], case_generations: [], runs: [], exports: [],
};

afterEach(() => vi.restoreAllMocks());

test("正式工作台固定显示五个产品页签，上传页明确不调用 AI", async () => {
  mockRequests();
  renderShell();

  expect(await screen.findByText("AI 测试用例生成平台")).toBeInTheDocument();
  expect(screen.getAllByRole("tab")).toHaveLength(5);
  expect(screen.getByRole("tab", { name: "1上传文档" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "2需求分析" })).toBeInTheDocument();
  expect(screen.getByText("本页面不调用 AI")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "上传并解析" })).toBeInTheDocument();
  expect(screen.queryByText(/批次/)).not.toBeInTheDocument();
});

test("需求分析页显示三种模式、完整筛选和分页条数", async () => {
  mockRequests(); const user = userEvent.setup(); renderShell();
  await screen.findByText("本页面不调用 AI");
  await user.click(screen.getByRole("tab", { name: "2需求分析" }));

  expect(screen.getByLabelText("真实模型（直接调用）")).toBeInTheDocument();
  expect(screen.getByLabelText("真实模型（Skill 工作流）")).toBeInTheDocument();
  expect(screen.getByLabelText("本地模式（不调用 AI）")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "需求分析筛选" })).toHaveTextContent("功能模块");
  expect(screen.getByRole("region", { name: "需求分析筛选" })).toHaveTextContent("功能点");
  expect(screen.getByRole("region", { name: "需求分析筛选" })).toHaveTextContent("分析状态");
  expect(screen.getByRole("combobox", { name: /每页/ })).toHaveTextContent("2050100");
});

test("审核可跳过并进入测试用例，模板是用例页第一项", async () => {
  mockRequests(); const user = userEvent.setup(); renderShell();
  await screen.findByText("本页面不调用 AI");
  await user.click(screen.getByRole("tab", { name: "4审核" }));
  await user.click(screen.getByRole("button", { name: "跳过审核，进入测试用例" }));

  expect(await screen.findByRole("heading", { name: "测试用例" })).toBeInTheDocument();
  expect(screen.getByText("1. 测试用例模板")).toBeInTheDocument();
  expect(screen.getByLabelText("使用默认测试用例模板")).toBeInTheDocument();
  expect(screen.getByText("2. 当前测试范围")).toBeInTheDocument();
  expect(screen.getByText("3. 生成模式")).toBeInTheDocument();
});

function renderShell() {
  return render(<WorkflowShell projectId={1} projectName="智能终端 v0.2" testObject="智能终端"
    softwareVersion="v0.2.0" onOpenProjects={() => undefined} />);
}

function mockRequests() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/workspace")) return new Response(JSON.stringify(workspace), { status: 200 });
    if (url.includes("/ai-session-config")) return new Response("null", { status: 200 });
    if (url.includes("/review-skip") && init?.method === "POST") return new Response(JSON.stringify({ skipped: true }), { status: 200 });
    if (url.includes("/case-template")) return new Response(JSON.stringify({ mode: "default", mapping: {
      id: 0, project_id: 1, version: 0, filename: "默认测试用例模板.xlsx", format: "xlsx", status: "confirmed",
      sheets: [{ name: "用例表", index: 0, role_suggestion: "case", role: "case", title_row_candidates: [1],
        title_row: 1, columns: [], participates: true, field_mapping: { "测试用例标题": "title" }, diagnostics: [] }],
      diagnostics: [], retained_sheet_names: ["用例表"], confirmed_by: "系统默认模板", confirmed_at: null,
    } }), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
}
