import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { RequirementImportPanel } from "./RequirementImportPanel";

afterEach(() => vi.restoreAllMocks());

test("混合文件上传后展示文件级解析状态、诊断与 Step 00 基线", async () => {
  let assetId = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/requirement-versions")) return json([]);
    if (url.endsWith("/assets") && init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      assetId += 1;
      return json({ id: assetId, name: body.name, media_type: body.media_type || "application/octet-stream" });
    }
    if (url.includes("/reparse") && init?.method === "POST") return json(packageResponse());
    if (url.endsWith("/requirement-packages") && init?.method === "POST") return json(packageResponse());
    return new Response("未处理请求", { status: 500 });
  });
  const user = userEvent.setup();
  render(<RequirementImportPanel projectId={1} testObject="采集设备" softwareVersion="v1.0.0" />);

  await user.upload(screen.getByLabelText("需求文件"), [
    new File(["# 测试标题"], "available.md", { type: "text/markdown" }),
    new File(["{broken:"], "broken.json", { type: "application/json" }),
  ]);
  await user.click(screen.getByRole("button", { name: "上传并解析" }));

  expect(await screen.findByRole("region", { name: "Step 00 材料基线" })).toHaveTextContent("测试对象：采集设备；软件版本：v1.0.0");
  expect(screen.getByText(/解析完整/)).toBeInTheDocument();
  expect(screen.getByText(/解析失败/)).toBeInTheDocument();
  expect(screen.getByText("结构化需求资料格式错误")).toBeInTheDocument();
  await user.click(screen.getByText("查看文档结构、章节/表格与来源位置"));
  expect(screen.getByText("文档标题：测试标题")).toBeInTheDocument();
  expect(screen.getAllByText("lines:1-1")).toHaveLength(2);
  await user.click(screen.getByRole("button", { name: "只重试失败项" }));
  expect(await screen.findByText("1 份可继续使用，1 份需要处理。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重新建立当前材料版本" })).toBeInTheDocument();
});

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function packageResponse() {
  return {
    id: 10, project_id: 1, name: "当前任务材料基线", status: "draft", published_version_id: null,
    diagnostics: [{ asset_id: 2, filename: "broken.json", code: "malformed_content", severity: "error", message: "结构化需求资料格式错误" }],
    created_at: "2026-09-25T00:00:00Z",
    materials: [
      { asset_id: 1, asset_revision: 1, filename: "available.md", media_type: "text/markdown", format: "markdown",
        sha256: "hash", size_bytes: 8, content_base64: "IyDmtYvor5U=", parse_status: "complete", diagnostics: [], visual_inferences: [],
        fragments: [{ text: "# 测试标题", kind: "heading", source_reference: { reference_id: "src-1", asset_id: 1, filename: "available.md", locator: "lines:1-1" } }] },
      { asset_id: 2, asset_revision: 1, filename: "broken.json", media_type: "application/json", format: "json",
        sha256: "hash", size_bytes: 10, content_base64: "eyJicm9rZW4iOg==", parse_status: "failed", visual_inferences: [],
        diagnostics: [{ asset_id: 2, filename: "broken.json", code: "malformed_content", severity: "error", message: "结构化需求资料格式错误" }], fragments: [] },
    ],
  };
}
