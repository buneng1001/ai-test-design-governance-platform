import { render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { CaseWorkspace } from "./CaseWorkspace";
import { ReviewWorkspace } from "./ReviewWorkspace";
import { SuggestionsWorkspace } from "./SuggestionsWorkspace";
import type { WorkspaceState } from "./v020_types";

afterEach(() => vi.restoreAllMocks());

const expectedRequirementHeaders = [
  "总序号", "模块", "测试项", "测试项依据", "测试项来源", "测试类型", "优先级", "关联需求ID",
];

test("新增建议和审核建议使用同一张需求点表，审核报告显示在表格之前", () => {
  const workspace = baseWorkspace();
  workspace.suggestions = [{
    id: "suggestion-1", project_id: 1, run_id: "run-s", suggestion_action: "add", module: "登录",
    test_item: "错误密码提示", test_basis: "缺少异常提示约束", test_source: "新增建议", test_type: "异常测试",
    priority: "P1", related_requirement_id: "REQ-1", related_analysis_row_id: null,
    content: "错误密码提示", ai_reason: "缺少异常提示约束", disposition: "pending",
  }];
  workspace.review_suggestions = [{
    id: "review-1", project_id: 1, run_id: "run-r", role: "product_manager", suggestion_action: "risk",
    module: "登录", test_item: "账号锁定策略", test_basis: "业务规则尚未明确", test_source: "AI 角色审核",
    test_type: "安全性测试", priority: "P0", related_requirement_id: "REQ-1", related_analysis_row_id: null,
    content: "账号锁定策略", ai_reason: "业务规则尚未明确", disposition: "pending",
  }];
  workspace.runs = [{
    id: "run-r", project_id: 1, page: "review", mode: "local", status: "completed", source_label: "本地模式",
    provider: "不适用", model: "不适用", credential_source: "不适用", input_summary: {
      file_count: 0, fragment_count: 0, analysis_row_count: 1, selected_row_count: 0,
      requirement_version_id: 1, roles: ["product_manager"],
    },
    prompt_version: "review.local.v1", skill_version: null, estimated_input_tokens: 1, max_output_tokens: 1,
    supplemental_notes: "", supplemental_requirements: "", template_filename: null,
    estimated_cost: { status: "unavailable" }, actual_usage: null, actual_cost: null, stage: "完成", stage_events: [],
    duration_ms: 1, started_at: "2026-10-14T00:00:00Z", completed_at: "2026-10-14T00:00:01Z", error: null,
    next_step: "", result_summary: { count: 1, label: "审核建议" },
    role_reports: [{ role: "product_manager", summary: "需求目标清楚，但锁定策略需补充。", strengths: ["目标清楚"], concerns: ["锁定规则缺失"] }],
  }];

  const suggestionView = render(<SuggestionsWorkspace projectId={1} workspace={workspace} onChanged={async () => undefined} />);
  expect(screen.getAllByRole("columnheader").map((item) => item.textContent)).toEqual(expectedRequirementHeaders);
  suggestionView.unmount();

  render(<ReviewWorkspace projectId={1} workspace={workspace} onChanged={async () => undefined} onSkip={() => undefined} />);
  expect(screen.getByRole("region", { name: "身份需求分析报告" })).toHaveTextContent("需求目标清楚，但锁定策略需补充。");
  expect(screen.getAllByRole("columnheader").map((item) => item.textContent)).toEqual(expectedRequirementHeaders);
});

test("测试用例预览严格使用当前模板列并提供默认模板下载", async () => {
  const headers = ["用例编号", "测试用例标题", "优先级", "预置条件", "输入", "操作步骤", "预期结果", "测试类型", "模块", "测试项", "附件", "软件版本"];
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    mode: "default", mapping: {
      id: 0, project_id: 1, version: 0, filename: "默认测试用例模板.xlsx", format: "xlsx", status: "confirmed",
      sheets: [{ name: "用例表", index: 0, role_suggestion: "case", role: "case", title_row_candidates: [1],
        title_row: 1, columns: headers.map((name, index) => ({ index: index + 1, name, sample_values: [] })),
        participates: true, field_mapping: Object.fromEntries(headers.map((name) => [name, name])), diagnostics: [] }],
      diagnostics: [], retained_sheet_names: ["用例表"], confirmed_by: "系统默认模板", confirmed_at: null,
    },
  }), { status: 200, headers: { "Content-Type": "application/json" } }));

  render(<CaseWorkspace projectId={1} workspace={baseWorkspace()} onChanged={async () => undefined} />);
  const table = await screen.findByRole("table", { name: "测试用例模板预览" });
  expect(within(table).getAllByRole("columnheader").map((item) => item.textContent)).toEqual(headers);
  expect(screen.getByRole("button", { name: "下载默认测试模板" })).toBeInTheDocument();
});

test("历史生成使用当时的模板快照而不是当前选择的模板", async () => {
  const workspace = baseWorkspace();
  workspace.active_run_ids = { cases: "run-history" };
  workspace.case_generations = [{
    id: "generation-history", project_id: 1, run_id: "run-history", scope_ids: [],
    supplemental_requirements: "", created_at: "2026-10-14T00:00:00Z",
    template: mappingWithHeaders(["历史用例编号", "历史用例标题"]),
  }];
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    mode: "default", mapping: mappingWithHeaders(["用例编号", "测试用例标题", "优先级"]),
  }), { status: 200, headers: { "Content-Type": "application/json" } }));

  render(<CaseWorkspace projectId={1} workspace={workspace} onChanged={async () => undefined} />);

  const table = await screen.findByRole("table", { name: "测试用例模板预览" });
  expect(within(table).getAllByRole("columnheader").map((item) => item.textContent))
    .toEqual(["历史用例编号", "历史用例标题"]);
});

function mappingWithHeaders(headers: string[]) {
  return {
    id: 0, project_id: 1, version: 0, filename: "模板.xlsx", format: "xlsx" as const, status: "confirmed" as const,
    sheets: [{ name: "用例表", index: 0, role_suggestion: "case" as const, role: "case" as const,
      title_row_candidates: [1], title_row: 1,
      columns: headers.map((name, index) => ({ index: index + 1, name, sample_values: [] })), participates: true,
      field_mapping: Object.fromEntries(headers.map((name, index) => [name, index ? "title" : "external_case_number"])),
      diagnostics: [] }],
    diagnostics: [], retained_sheet_names: ["用例表"], confirmed_by: "测试", confirmed_at: null,
  };
}

function baseWorkspace(): WorkspaceState {
  return {
    project_id: 1, supplemental_notes: "", requirement_version: null,
    template: { mode: "default", mapping_id: null }, analysis_rows: [], suggestions: [], review_suggestions: [],
    cases: [], case_generations: [], runs: [], exports: [],
  };
}
