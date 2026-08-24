import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";


afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});


test("测试工程师创建测试设计项目后进入项目工作台", async () => {
  const user = userEvent.setup();
  const createdProject = {
    id: 1,
    name: "智能采集设备测试设计",
    test_object: "虚构智能采集设备",
    description: "验证通用采集能力",
    settings: { requirement_language: "zh-CN" },
    created_at: "2026-08-24T00:00:00Z",
    updated_at: "2026-08-24T00:00:00Z",
  };
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(createdProject), { status: 201 }));

  render(<App />);

  expect(await screen.findByText("还没有测试设计项目")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "创建测试设计项目" }));
  await user.type(screen.getByLabelText("项目名称"), createdProject.name);
  await user.type(screen.getByLabelText("测试对象"), createdProject.test_object);
  await user.type(screen.getByLabelText("项目描述"), createdProject.description);
  await user.click(screen.getByRole("button", { name: "创建并进入工作台" }));

  expect(await screen.findByRole("heading", { name: createdProject.name })).toBeInTheDocument();
  expect(screen.getByText("项目工作台")).toBeInTheDocument();
  expect(screen.getByText(`测试对象：${createdProject.test_object}`)).toBeInTheDocument();
  expect(window.location.pathname).toBe("/projects/1");
});
