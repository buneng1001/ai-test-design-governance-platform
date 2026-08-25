import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CoveragePanel } from "./CoveragePanel";

describe("CoveragePanel", () => {
  it("loads a metric and exposes its gap, quality issue, and evidence details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        metrics: {
          requirement_coverage: {
            label: "需求", numerator: 1, denominator: 2, percentage: 50,
            covered_items: ["REQ-1"], uncovered_items: ["REQ-2"], high_risk_gaps: [],
            quality_issues: [{ id: 7, phenomenon: "状态展示不一致", severity: "high" }],
            execution_evidence: [{ id: 9, stable_case_id: "CASE-1", evidence_references: ["evidence://1"] }],
          },
        },
      }),
    }));
    render(<CoveragePanel projectId={1} />);
    fireEvent.change(screen.getByLabelText("需求版本 ID"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("测试设计 ID"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("用例评审批次 ID"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "查看治理指标" }));
    await waitFor(() => expect(screen.getByText(/未覆盖项：REQ-2/)).toBeInTheDocument());
    expect(screen.getByText(/状态展示不一致/)).toBeInTheDocument();
    expect(screen.getByText(/evidence:\/\/1/)).toBeInTheDocument();
  });
});
