import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { TestDesignPanel } from "./TestDesignPanel";

test("测试工程师可以创建并确认测试设计", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify({
      id: 1,
      requirement_version_id: 1,
      status: "draft",
      dimensions: [{ id: "dimension-1", name: "功能", status: "active" }],
      scope_items: [{ id: "scope-1", title: "设备保存状态", primary_dimension_id: "dimension-1" }],
      risks: [{
        scope_item_id: "scope-1", final_score: 60, risk_level: "medium", priority: "P1",
        factors: [{ key: "business_impact", name: "业务影响", score: 3, weight: 1, source_references: [] }],
      }],
      automation_candidates: [{
        scope_item_id: "scope-1", suggested_score: 50, decision: "manual_execution", suggestion_reason: "需要人工观察",
        factors: {
          regression_value: 3, determinism: 3, environment_control: 3, saving_benefit: 3,
          maintenance_cost: 3, manual_observation: 3,
        },
      }],
      confirmed_by: null,
    }), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      id: 1,
      requirement_version_id: 1,
      status: "confirmed",
      dimensions: [{ id: "dimension-1", name: "功能", status: "active" }],
      scope_items: [{ id: "scope-1", title: "设备保存状态", primary_dimension_id: "dimension-1" }],
      risks: [{
        scope_item_id: "scope-1", final_score: 60, risk_level: "medium", priority: "P1",
        factors: [{ key: "business_impact", name: "业务影响", score: 3, weight: 1, source_references: [] }],
      }],
      automation_candidates: [{
        scope_item_id: "scope-1", suggested_score: 50, decision: "manual_execution", suggestion_reason: "需要人工观察",
        factors: {
          regression_value: 3, determinism: 3, environment_control: 3, saving_benefit: 3,
          maintenance_cost: 3, manual_observation: 3,
        },
      }],
      confirmed_by: "测试工程师",
    }), { status: 200 }));

  render(<TestDesignPanel projectId={1} />);
  await user.click(screen.getByRole("button", { name: "生成测试设计候选" }));
  expect(await screen.findByText(/设备保存状态/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "确认测试设计" }));
  expect(await screen.findByText("状态：设计已确认")).toBeInTheDocument();
});
