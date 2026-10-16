import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { WorkflowRunControls } from "./WorkflowRunControls";

afterEach(() => vi.restoreAllMocks());

test("真实模型先展示输入与成本确认，取消时不会调用模型", async () => {
  const user = userEvent.setup();
  const onRun = vi.fn(async () => undefined);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    page: "analysis", mode: "direct", provider: "custom", model: "verified-model",
    credential_source: "session", verification_status: "verified",
    input_summary: { file_count: 2, fragment_count: 8, analysis_row_count: 0, selected_row_count: 0,
      requirement_version_id: 3, roles: [] }, supplemental_notes: "关注异常流程",
    supplemental_requirements: "", template_filename: null,
    prompt_version: "requirement-analysis.direct.v1", skill_version: null,
    estimated_input_tokens: 1280, max_output_tokens: 10000, model_timeout_seconds: 120,
    estimated_cost: { status: "unavailable", reason: "未登记单价" }, requires_confirmation: true,
  }), { status: 200, headers: { "Content-Type": "application/json" } }));

  render(<WorkflowRunControls projectId={1} page="analysis" actionLabel="开始需求分析" onRun={onRun} />);
  expect(screen.getByText("运行状态：尚未执行")).toBeInTheDocument();
  await user.click(screen.getByLabelText("真实模型（直接调用）"));
  await user.click(screen.getByRole("button", { name: "查看调用范围" }));

  expect(await screen.findByRole("region", { name: "真实模型调用确认" })).toHaveTextContent("2 份资料、8 个来源片段");
  expect(screen.getByRole("region", { name: "真实模型调用确认" })).toHaveTextContent("输入约 1,280");
  expect(screen.getByRole("region", { name: "真实模型调用确认" })).toHaveTextContent("模型响应超时120 秒");
  expect(screen.getByRole("region", { name: "真实模型调用确认" })).toHaveTextContent("不可获得：未登记单价");
  expect(onRun).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "取消" }));
  expect(onRun).not.toHaveBeenCalled();
});

test("相同输入命中已有结果时明确提示未再次调用模型", async () => {
  const user = userEvent.setup();
  const onRun = vi.fn(async () => ({ reused: true }));
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    page: "analysis", mode: "local", provider: "不适用", model: "不适用",
    credential_source: "不适用", verification_status: "本地模式无需验证",
    input_summary: { file_count: 1, fragment_count: 1, source_fragment_count: 3,
      context_chunk_count: 1, analysis_row_count: 0, selected_row_count: 0,
      requirement_version_id: 1, roles: [] }, supplemental_notes: "",
    supplemental_requirements: "", template_filename: null,
    prompt_version: "analysis.local.v2", skill_version: null,
    estimated_input_tokens: 320, max_output_tokens: 10000,
    estimated_cost: { status: "unavailable", reason: "本地模式" }, requires_confirmation: false,
  }), { status: 200, headers: { "Content-Type": "application/json" } }));

  render(<WorkflowRunControls projectId={1} page="analysis" actionLabel="开始需求分析" onRun={onRun} />);
  await user.click(screen.getByRole("button", { name: "开始需求分析" }));

  expect((await screen.findByText(/输入与配置未变化/)).closest("p"))
    .toHaveTextContent("未再次调用模型，也未新增结果");
  expect(onRun).toHaveBeenCalledWith("local", true);
});
