import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { AnalysisWorkspace } from "./AnalysisWorkspace";
import type { AnalysisRow, RunEvidence, WorkspaceState } from "./v020_types";

afterEach(() => vi.restoreAllMocks());

test("需求分析大表只渲染当前页并按结果 ID 持久化跨页勾选", async () => {
  const user = userEvent.setup();
  const rows = Array.from({ length: 25 }, (_, index) => analysisRow(index + 1));
  const workspace: WorkspaceState = {
    project_id: 1, supplemental_notes: "", requirement_version: {} as WorkspaceState["requirement_version"],
    template: { mode: "default", mapping_id: null }, analysis_rows: rows, suggestions: [],
    review_suggestions: [], cases: [], case_generations: [], runs: [], exports: [],
  };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    selected_count: 1, affected_count: 1,
  }), { status: 200, headers: { "Content-Type": "application/json" } }));
  render(<AnalysisWorkspace projectId={1} workspace={workspace} onChanged={vi.fn(async () => undefined)} />);

  expect(screen.getAllByRole("columnheader").map((item) => item.textContent)).toEqual([
    "纳入范围", "总序号", "模块", "测试项", "测试项依据", "测试项来源", "测试类型", "优先级", "关联需求ID",
  ]);

  expect(screen.getAllByRole("checkbox")).toHaveLength(20);
  expect(screen.getByText("第 1 / 2 页")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getAllByRole("checkbox")).toHaveLength(5);
  await user.click(screen.getByLabelText("选择-测试项 21"));

  expect(fetchMock).toHaveBeenCalledWith("/api/v0.2/projects/1/analysis-selection", expect.objectContaining({
    method: "PATCH", body: JSON.stringify({ row_ids: ["row-21"], selected: true }),
  }));
  expect(within(screen.getByRole("region", { name: "需求分析筛选" })).getByRole("button", {
    name: "全选当前筛选结果（25）",
  })).toBeInTheDocument();
});

test("可先让 AI 阅读整理资料并在确认后发起独立运行", async () => {
  const user = userEvent.setup();
  const workspace: WorkspaceState = {
    project_id: 1, supplemental_notes: "", requirement_version: {} as WorkspaceState["requirement_version"],
    template: { mode: "default", mapping_id: null }, analysis_rows: [], suggestions: [],
    review_suggestions: [], cases: [], case_generations: [], runs: [], exports: [],
  };
  const preflight = {
    page: "understanding", mode: "direct", provider: "硅基流动", model: "Qwen3.5-27B",
    credential_source: "会话配置", verification_status: "verified", input_summary: {
      file_count: 1, fragment_count: 2, source_fragment_count: 4, context_chunk_count: 2,
      analysis_row_count: 0, selected_row_count: 0, requirement_version_id: 1, roles: [],
    }, supplemental_notes: "", supplemental_requirements: "", template_filename: null,
    prompt_version: "material-understanding.direct.v1", skill_version: null,
    estimated_input_tokens: 1200, max_output_tokens: 4000,
    estimated_cost: { status: "unavailable", reason: "未登记价格" }, requires_confirmation: true,
  };
  const completed = {
    run: { id: "understanding-1" }, reused: false,
    understanding: { overview: "已理解资料", organized_fragments: [] },
  };
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(preflight), {
      status: 200, headers: { "Content-Type": "application/json" },
    }))
    .mockResolvedValueOnce(new Response(JSON.stringify(completed), {
      status: 201, headers: { "Content-Type": "application/json" },
    }));

  render(<AnalysisWorkspace projectId={1} workspace={workspace} onChanged={vi.fn(async () => undefined)} />);
  await user.click(screen.getByRole("button", { name: "AI 阅读并整理资料（先确认范围）" }));
  expect(await screen.findByRole("region", { name: "真实模型调用确认" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "确认并执行：AI 阅读并整理资料" }));

  expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/v0.2/projects/1/material-understanding-runs",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ mode: "direct", confirmed: true }) }));
});

test("模型调用超时后刷新并显示已保存的失败运行而不是尚未执行", async () => {
  const user = userEvent.setup();
  const initial = emptyWorkspace();
  const failedRun = timeoutRun();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(runPreflight()), {
      status: 200, headers: { "Content-Type": "application/json" },
    }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: {
      user_message: "模型服务在需求分析阶段等待 120 秒后仍未返回",
      suggested_action: "检查网络或模型负载后重试", retryable: true,
    } }), { status: 504, headers: { "Content-Type": "application/json" } }));

  function Harness() {
    const [workspace, setWorkspace] = useState(initial);
    return <AnalysisWorkspace projectId={1} workspace={workspace} onChanged={async () => {
      setWorkspace({ ...initial, active_run_ids: {}, runs: [failedRun] });
    }} />;
  }

  render(<Harness />);
  await user.click(screen.getByLabelText("真实模型（直接调用）"));
  await user.click(screen.getByRole("button", { name: /开始需求分析|查看调用范围/ }));
  await user.click(await screen.findByRole("button", { name: /确认.*开始需求分析/ }));

  const analysisControls = screen.getByRole("region", { name: "开始需求分析运行设置" });
  expect(await within(analysisControls).findByText("运行状态：失败")).toBeInTheDocument();
  expect(within(analysisControls).queryByText("运行状态：尚未执行")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

function emptyWorkspace(): WorkspaceState {
  return {
    project_id: 1, supplemental_notes: "", requirement_version: {} as WorkspaceState["requirement_version"],
    template: { mode: "default", mapping_id: null }, analysis_rows: [], suggestions: [],
    review_suggestions: [], cases: [], case_generations: [], runs: [], exports: [],
  };
}

function runPreflight() {
  return {
    page: "analysis", mode: "direct", provider: "硅基流动", model: "Qwen3.5-27B",
    credential_source: "会话配置", verification_status: "verified", input_summary: {
      file_count: 1, fragment_count: 1, source_fragment_count: 3, context_chunk_count: 1,
      analysis_row_count: 0, selected_row_count: 0, requirement_version_id: 1, roles: [],
    }, supplemental_notes: "", supplemental_requirements: "", template_filename: null,
    prompt_version: "requirement-analysis.direct.v2", skill_version: null,
    estimated_input_tokens: 1200, max_output_tokens: 10000,
    estimated_cost: { status: "unavailable", reason: "未登记价格" }, requires_confirmation: true,
  };
}

function timeoutRun(): RunEvidence {
  return {
    id: "run-timeout", project_id: 1, page: "analysis", mode: "direct", status: "failed",
    source_label: "真实模型（直接调用）", provider: "硅基流动", model: "Qwen3.5-27B",
    credential_source: "会话配置", input_summary: runPreflight().input_summary,
    prompt_version: "requirement-analysis.direct.v2", skill_version: null,
    estimated_input_tokens: 1200, max_output_tokens: 10000, supplemental_notes: "",
    supplemental_requirements: "", template_filename: null,
    estimated_cost: { status: "unavailable", reason: "未登记价格" },
    actual_usage: { status: "unavailable", reason: "运行失败" },
    actual_cost: { status: "unavailable", reason: "运行失败" }, stage: "失败",
    stage_events: [{ stage: "调用模型", status: "failed", detail: "模型服务超时" }],
    duration_ms: 120000, started_at: "2026-10-16T00:00:00Z", completed_at: "2026-10-16T00:02:00Z",
    error: "模型服务在需求分析阶段等待 120 秒后仍未返回。建议检查网络或模型负载后重试。",
    next_step: "检查网络或模型负载后重试。", result_summary: null,
  };
}

function analysisRow(index: number): AnalysisRow {
  return {
    id: `row-${index}`, project_id: 1, run_id: "run-1", module: `模块 ${Math.ceil(index / 5)}`,
    function_point: `功能点 ${index}`, test_item: `测试项 ${index}`, test_point: `测试点 ${index}`,
    source_reference_id: `input-${index}`, source: "requirements.md · 第1节", source_reference: {},
    ai_reason: "需求明确", information_gap: "", status: "ready", selected: false,
    origin: "analysis", mode: "local", total_index: index, test_basis: "需求明确",
    test_source: "requirements.md · 第1节", test_type: "功能测试", priority: "P1",
    related_requirement_id: `REQ-${index}`,
  };
}
