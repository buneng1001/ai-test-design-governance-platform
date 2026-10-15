import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ModelConfigPanel } from "./ModelConfigPanel";

const jsonResponse = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

const siliconflowProviders = (models: string[]) => jsonResponse([{
  id: "siliconflow", name: "硅基流动", base_url: "https://api.siliconflow.cn/v1",
  models: models.map((id) => ({ id, state: "preset" })),
}]);

const siliconflowStatus = (
  model: string, modelState: string, verificationStatus: string,
  credentialSource = "remembered_local", validatedAt: string | null = null,
) => jsonResponse({
  provider: "siliconflow", model, base_url: "https://api.siliconflow.cn/v1",
  credential_source: credentialSource, credential_configured: true,
  model_options: [{ id: model, state: modelState }],
  verification_status: verificationStatus, validated_at: validatedAt,
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

test("模型配置只发送临时 Key，不写入浏览器本地存储", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(siliconflowProviders(["Qwen/Qwen3-8B"]))
    .mockResolvedValueOnce(jsonResponse(null))
    .mockResolvedValueOnce(siliconflowStatus("Qwen/Qwen3-8B", "preset", "unverified", "temporary"));

  render(<ModelConfigPanel />);

  await screen.findByRole("button", { name: "保存配置" });
  await user.type(screen.getByLabelText("API Key"), "temporary-secret");
  await user.click(screen.getByRole("button", { name: "保存配置" }));

  const [, saveRequest] = fetchMock.mock.calls[2];
  expect(saveRequest?.body).toContain("temporary-secret");
  expect(localStorage.getItem("ai-test-design-model-config")).toBeNull();
  expect(await screen.findByText(/凭据来源：临时 Key/)).toBeInTheDocument();
});

test("刷新模型后不会继续使用已不在最新列表中的上次模型", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(siliconflowProviders(["Qwen/Qwen3.5-27B"]))
    .mockResolvedValueOnce(siliconflowStatus(
      "Qwen/Qwen3.5-27B", "verified", "verified", "remembered_local", "2026-10-07T08:50:54Z",
    ))
    .mockResolvedValueOnce(jsonResponse({
      success: true, provider: "siliconflow",
      models: [{ id: "Qwen/Qwen3.6-27B", state: "discovered" }], error: null,
    }));

  render(<ModelConfigPanel />);

  const modelInput = await screen.findByLabelText("模型");
  expect(modelInput).toHaveValue("");
  expect(screen.getByRole("status")).toHaveTextContent("为避免误用历史模型，本次未自动选择");
  expect(screen.getByRole("button", { name: "连接测试" })).toBeDisabled();

  await user.type(modelInput, "Qwen/Qwen3.5-27B");

  await user.click(screen.getByRole("button", { name: "发现模型" }));

  expect(screen.getByLabelText("模型")).toHaveValue("");
  expect(screen.getByRole("status")).toHaveTextContent("上次选择的模型不在最新列表中，请重新选择");
  expect(screen.getByRole("button", { name: "连接测试" })).toBeDisabled();
});

test("修改模型后旧验证状态失效并明确测试本次模型", async () => {
  const user = userEvent.setup();
  let resolveConnection!: (response: Response) => void;
  const pendingConnection = new Promise<Response>((resolve) => { resolveConnection = resolve; });
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(siliconflowProviders(["Qwen/Qwen3.5-27B", "Qwen/Qwen3.6-27B"]))
    .mockResolvedValueOnce(siliconflowStatus(
      "Qwen/Qwen3.5-27B", "verified", "verified", "remembered_local", "2026-10-07T08:50:54Z",
    ))
    .mockImplementationOnce(() => pendingConnection)
    .mockResolvedValueOnce(siliconflowStatus(
      "Qwen/Qwen3.6-27B", "verified", "verified", "remembered_local", "2026-10-13T06:40:00Z",
    ));

  render(<ModelConfigPanel />);

  const modelInput = await screen.findByLabelText("模型");
  expect(modelInput).toHaveValue("");
  expect(screen.getByText("当前模型状态：待重新测试")).toBeInTheDocument();
  await user.type(modelInput, "Qwen/Qwen3.5-27B");
  await user.type(screen.getByLabelText("API Key"), "new-temporary-key");
  expect(screen.getByText("当前模型状态：待重新测试")).toBeInTheDocument();
  await user.clear(modelInput);
  await user.type(modelInput, "Qwen/Qwen3.6-27B");
  expect(screen.getByRole("status")).toHaveTextContent("配置已修改，请重新测试连接");
  expect(screen.queryByText(/连接状态：已验证/)).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "连接测试" }));
  expect(screen.getByRole("button", { name: "正在测试…" })).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("正在测试：siliconflow / Qwen/Qwen3.6-27B");

  const requestBody = JSON.parse(String(fetchMock.mock.calls[2][1]?.body));
  expect(requestBody.model).toBe("Qwen/Qwen3.6-27B");

  resolveConnection(jsonResponse({
    success: true, message: "模型连接测试成功", provider: "siliconflow",
    model: "Qwen/Qwen3.6-27B", error: null,
  }));
  expect(await screen.findByText("模型连接测试成功：siliconflow / Qwen/Qwen3.6-27B")).toBeInTheDocument();
});

test("连接测试显示响应超时的截止时间和错误类型", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(siliconflowProviders(["Qwen/Qwen3.5-27B"]))
    .mockResolvedValueOnce(jsonResponse(null))
    .mockResolvedValueOnce(jsonResponse({
      success: false, message: null, provider: "siliconflow", model: "Qwen/Qwen3.5-27B",
      error: {
        stage: "connection_test", provider: "siliconflow", model: "Qwen/Qwen3.5-27B",
        error_type: "response_timeout", retryable: true,
        user_message: "模型服务在连接测试时未及时返回",
        suggested_action: "检查模型负载后重试，或改用其他可用模型",
        detail: "单次网络等待上限 20 秒",
      },
    }))
    .mockResolvedValueOnce(siliconflowStatus("Qwen/Qwen3.5-27B", "failed", "failed"));

  render(<ModelConfigPanel />);
  await screen.findByRole("button", { name: "连接测试" });
  await user.click(screen.getByRole("button", { name: "连接测试" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "模型服务在连接测试时未及时返回。建议：检查模型负载后重试，或改用其他可用模型（错误类型：response_timeout；单次网络等待上限 20 秒；可重试）",
  );
});

test("发现大量模型后在页面流内展示完整可筛选列表", async () => {
  const user = userEvent.setup();
  const models = Array.from({ length: 98 }, (_, index) => `provider/model-${index + 1}`);
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(siliconflowProviders(["Qwen/Qwen3-8B"]))
    .mockResolvedValueOnce(jsonResponse(null))
    .mockResolvedValueOnce(jsonResponse({
      success: true, provider: "siliconflow",
      models: models.map((id) => ({ id, state: "discovered" })), error: null,
    }));

  render(<ModelConfigPanel />);
  await screen.findByRole("button", { name: "发现模型" });
  await user.click(screen.getByRole("button", { name: "发现模型" }));
  await user.click(screen.getByRole("button", { name: "选择模型（98）" }));

  const list = screen.getByRole("listbox", { name: "可用模型" });
  expect(list).toHaveAttribute("data-scroll-container", "page");
  expect(within(list).getAllByRole("option")).toHaveLength(98);
  expect(within(list).getByRole("option", { name: /provider\/model-98/ })).toBeInTheDocument();
  expect(screen.getByLabelText("模型")).not.toHaveAttribute("list");

  await user.type(screen.getByLabelText("筛选模型"), "model-98");
  expect(within(list).getAllByRole("option")).toHaveLength(1);
});

test("可以选择自动代理回退并随连接测试提交", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(siliconflowProviders(["Qwen/Qwen3-8B"]))
    .mockResolvedValueOnce(jsonResponse(null))
    .mockResolvedValueOnce(jsonResponse({
      success: true, message: "模型连接测试成功", provider: "siliconflow",
      model: "Qwen/Qwen3-8B", error: null,
    }))
    .mockResolvedValueOnce(siliconflowStatus("Qwen/Qwen3-8B", "verified", "verified"));

  render(<ModelConfigPanel />);
  await screen.findByRole("button", { name: "连接测试" });
  expect(screen.getByLabelText("网络连接方式")).toHaveValue("auto");
  expect(screen.getByText(/关闭 VPN 后无需清除配置/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "连接测试" }));

  const requestBody = JSON.parse(String(fetchMock.mock.calls[2][1]?.body));
  expect(requestBody.network_mode).toBe("auto");
});
