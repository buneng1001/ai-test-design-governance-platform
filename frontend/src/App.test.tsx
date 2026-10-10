import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

const createdProject = {
  id: 1,
  name: "智能采集设备测试设计",
  test_object: "虚构智能采集设备",
  software_version: "v1.0.0",
  description: "验证通用采集能力",
  settings: { requirement_language: "zh-CN" },
  created_at: "2026-08-24T00:00:00Z",
  updated_at: "2026-08-24T00:00:00Z",
};

const emptyWorkspace = {
  project_id: 1, supplemental_notes: "", requirement_version: null,
  template: { mode: "default", mapping_id: null }, analysis_rows: [], suggestions: [],
  review_suggestions: [], cases: [], case_generations: [], runs: [], exports: [],
};

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

test("测试工程师创建测试设计项目后进入正式工作台", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url === "/api/v0.2/projects?archived=false") return response([]);
    if (url === "/api/projects" && init?.method === "POST") return response(createdProject, 201);
    if (url === "/api/projects/1") return response(createdProject);
    if (url.endsWith("/workspace")) return response(emptyWorkspace);
    if (url.endsWith("/ai-session-config")) return response(null);
    return response({});
  });

  render(<App />);

  expect(await screen.findByText("还没有测试设计项目")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "新建测试设计项目" }));
  await user.type(screen.getByLabelText("项目名称"), createdProject.name);
  await user.type(screen.getByLabelText("测试对象"), createdProject.test_object);
  await user.type(screen.getByLabelText("软件版本"), createdProject.software_version);
  await user.type(screen.getByLabelText("项目描述"), createdProject.description);
  await user.click(screen.getByRole("button", { name: "创建并进入工作台" }));

  expect(await screen.findByText("AI 测试用例生成平台")).toBeInTheDocument();
  expect(screen.getByText("当前测试设计项目").parentElement).toHaveTextContent(createdProject.name);
  expect(screen.getAllByRole("tab")).toHaveLength(5);
  expect(window.location.pathname).toBe("/projects/1");
});

test("项目管理区显示按项目持久化状态和归档入口", async () => {
  const user = userEvent.setup();
  const summary = {
    ...createdProject, archived: false, current_requirement_version: 3,
    latest_analysis_status: "已完成", latest_case_status: "已生成", latest_export_at: null,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/v0.2/projects?archived=false") return response([summary]);
    if (url === "/api/v0.2/projects?archived=true") return response([]);
    return response({});
  });

  render(<App />);

  expect(await screen.findByText(createdProject.name)).toBeInTheDocument();
  expect(screen.getByText(/需求版本：3/)).toHaveTextContent("分析：已完成 · 用例：已生成");
  expect(screen.getByRole("button", { name: "下载交付包" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "已归档" }));
  expect(await screen.findByText("没有已归档项目")).toBeInTheDocument();
});

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
