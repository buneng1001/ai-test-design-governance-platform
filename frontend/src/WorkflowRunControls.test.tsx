import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { decodeEntities, RunEvidenceCard, WorkflowRunControls } from "./WorkflowRunControls";

afterEach(() => vi.restoreAllMocks());

test("真实模型先展示输入与成本确认，取消时不会调用模型", async () => {
  const user = userEvent.setup();
  const onRun = vi.fn(async () => undefined);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    page: "analysis", mode: "skill", provider: "custom", model: "verified-model",
    credential_source: "session", verification_status: "verified",
    input_summary: { file_count: 2, fragment_count: 8, analysis_row_count: 0, selected_row_count: 0,
      requirement_version_id: 3, roles: [] }, supplemental_notes: "关注异常流程",
    supplemental_requirements: "", template_filename: null,
    prompt_version: "requirement-analysis.skill.v7", skill_version: "ai-test-design-requirement-analysis.v1",
    estimated_input_tokens: 1280, max_output_tokens: 4000, request_count: 7, max_request_count: 21,
    max_total_output_tokens: 56000,
    retry_policy: { max_retries_per_batch: 1, max_additional_requests: 7 },
    repair_policy: { max_requests_per_batch: 1, max_additional_requests: 7 }, model_timeout_seconds: 120,
    estimated_cost: { status: "unavailable", reason: "未登记单价" }, requires_confirmation: true,
  }), { status: 200, headers: { "Content-Type": "application/json" } }));

  render(<WorkflowRunControls projectId={1} page="analysis" actionLabel="开始需求分析" onRun={onRun} />);
  expect(screen.getByText("运行状态：尚未执行")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "查看调用范围" }));

  expect(await screen.findByRole("region", { name: "真实模型调用确认" })).toHaveTextContent("2 份资料、8 个来源片段");
  expect(screen.getByRole("region", { name: "真实模型调用确认" })).toHaveTextContent("所有常规批次输入合计约 1,280");
  expect(screen.getByRole("region", { name: "真实模型调用确认" }))
    .toHaveTextContent("预计常规调用模型 7 次；可重试连接错误每批最多重试 1 次；输出字段不完整时每批最多修复 1 次；不含自适应缩小范围时最多调用 21 次");
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
  await user.click(screen.getByLabelText("本地模式（不调用 AI）"));
  await user.click(screen.getByRole("button", { name: "开始需求分析" }));

  expect((await screen.findByText(/输入与配置未变化/)).closest("p"))
    .toHaveTextContent("未再次调用模型，也未新增结果");
  expect(onRun).toHaveBeenCalledWith("local", true);
});

test("真实模型运行中展示保存进度并允许停止", async () => {
  const user = userEvent.setup();
  const onRun = vi.fn(() => new Promise<void>(() => undefined));
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/cancel")) return new Response(JSON.stringify({
      id: url.split("/").at(-2), project_id: 1, page: "analysis", mode: "skill", status: "running",
      cancel_requested: true, source_label: "真实模型（直接调用）", provider: "custom", model: "m",
      credential_source: "session", input_summary: { file_count: 1, fragment_count: 4, analysis_row_count: 0,
        selected_row_count: 0, requirement_version_id: 1, roles: [] }, prompt_version: "v3", skill_version: null,
      estimated_input_tokens: 100, max_output_tokens: 3000, supplemental_notes: "", supplemental_requirements: "",
      template_filename: null, estimated_cost: { status: "unavailable" }, actual_usage: null, actual_cost: null,
      stage: "模型请求已完成 1/2", stage_events: [], duration_ms: null, started_at: "", completed_at: null,
      error: null, next_step: "正在停止", result_summary: null,
      progress: { completed_units: 1, total_units: 2, stage: "调用模型" },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
    return new Response(JSON.stringify({
      page: "analysis", mode: "skill", provider: "custom", model: "m", credential_source: "session",
      verification_status: "verified", input_summary: { file_count: 1, fragment_count: 4, analysis_row_count: 0,
        selected_row_count: 0, requirement_version_id: 1, roles: [] }, supplemental_notes: "",
      supplemental_requirements: "", template_filename: null, prompt_version: "v3", skill_version: null,
      estimated_input_tokens: 100, max_output_tokens: 3000, request_count: 2,
      estimated_cost: { status: "unavailable" }, requires_confirmation: true,
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  });

  render(<WorkflowRunControls projectId={1} page="analysis" actionLabel="开始需求分析" onRun={onRun} />);
  await user.click(screen.getByRole("button", { name: "查看调用范围" }));
  await user.click(await screen.findByRole("button", { name: "确认并开始需求分析" }));
  expect(await screen.findByText("本次调用信息（已确认并发送）")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "确认并开始需求分析" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "取消" })).not.toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "停止本次运行" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "停止本次运行" }));
  expect(await screen.findByText("Skill 阶段进度 1/2；已完成阶段均已保存检查点。")).toBeInTheDocument();
});

test("运行建议中的历史 HTML 实体会还原为正常中文", () => {
  expect(decodeEntities("&#x6839;据失败原因重试&amp;检查网络")).toBe("根据失败原因重试&检查网络");
  render(<RunEvidenceCard run={{
    id: "run-1", project_id: 1, page: "analysis", mode: "direct", status: "failed",
    source_label: "真实模型", provider: "custom", model: "m", credential_source: "session",
    input_summary: { file_count: 1, fragment_count: 1, analysis_row_count: 0, selected_row_count: 0,
      requirement_version_id: 1, roles: [] }, prompt_version: "v3", skill_version: null,
    estimated_input_tokens: 10, max_output_tokens: 10, supplemental_notes: "", supplemental_requirements: "",
    template_filename: null, estimated_cost: { status: "unavailable" }, actual_usage: null, actual_cost: null,
    stage: "失败", stage_events: [], duration_ms: 10, started_at: "", completed_at: "", error: "超时",
    next_step: "&#x6839;据失败原因重试", result_summary: null,
    attempts: [{ unit: 1, stage_id: "S00", attempt: 1, error_code: "provider_response_truncated",
      finish_reason: "length", response_length: 8192, diagnostic: "finish_reason=length" }],
  }} />);
  expect(screen.getByText(/根据失败原因重试/)).toBeInTheDocument();
  expect(screen.getByText(/S00.*finish_reason=length.*响应长度=8192/)).toBeInTheDocument();
});
