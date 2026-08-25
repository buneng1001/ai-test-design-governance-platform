import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportsPanel } from "./ReportsPanel";

describe("ReportsPanel", () => {
  it("exposes three independent downloads and visible Mock audit status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ summary: { ai_runs: [{ is_mock: true }] } }),
    }));
    render(<ReportsPanel projectId={7} />);

    expect(screen.getByRole("link", { name: "下载测试设计报告" })).toHaveAttribute(
      "href", "/api/projects/7/reports/test-design/download",
    );
    expect(screen.getByRole("link", { name: "下载执行与治理报告" })).toHaveAttribute(
      "href", "/api/projects/7/reports/execution-governance/download",
    );
    expect(screen.getByRole("link", { name: "下载审计包" })).toHaveAttribute(
      "href", "/api/projects/7/reports/audit-package/download",
    );

    fireEvent.click(screen.getByRole("button", { name: "检查 Mock 与审计摘要" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Mock AI 运行 1 条"));
  });
});
