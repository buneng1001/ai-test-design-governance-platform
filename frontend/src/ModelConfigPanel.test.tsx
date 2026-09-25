import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ModelConfigPanel } from "./ModelConfigPanel";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

test("模型配置只发送临时 Key，不写入浏览器本地存储", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([{
      id: "siliconflow", name: "硅基流动", base_url: "https://api.siliconflow.cn/v1",
      models: [{ id: "Qwen/Qwen3-8B", state: "preset" }],
    }]), { status: 200 }))
    .mockResolvedValueOnce(new Response("null", { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      provider: "siliconflow", model: "Qwen/Qwen3-8B", base_url: "https://api.siliconflow.cn/v1",
      credential_source: "temporary", credential_configured: true,
      model_options: [{ id: "Qwen/Qwen3-8B", state: "preset" }],
      verification_status: "unverified", validated_at: null,
    }), { status: 200 }));

  render(<ModelConfigPanel />);

  await screen.findByRole("button", { name: "保存配置" });
  await user.type(screen.getByLabelText("API Key"), "temporary-secret");
  await user.click(screen.getByRole("button", { name: "保存配置" }));

  const [, saveRequest] = fetchMock.mock.calls[2];
  expect(saveRequest?.body).toContain("temporary-secret");
  expect(localStorage.getItem("ai-test-design-model-config")).toBeNull();
  expect(await screen.findByText(/凭据来源：临时 Key/)).toBeInTheDocument();
});
