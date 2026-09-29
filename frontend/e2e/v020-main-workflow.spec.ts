import { expect, test } from "@playwright/test";

test.setTimeout(120_000);

test("普通用户无需进入高级治理即可从小型需求包导出用例", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "创建测试设计项目" }).click();
  await page.getByLabel("项目名称").fill("v0.2 浏览器验收项目");
  await page.getByLabel("测试对象").fill("受控智能设备");
  await page.getByLabel("软件版本").fill("v0.2.0");
  await page.getByRole("button", { name: "创建并进入工作台" }).click();

  await page.getByLabel("需求文件").setInputFiles({
    name: "controlled-requirements.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("设备必须返回当前状态，并在状态变化时记录时间戳。"),
  });
  await page.getByRole("button", { name: "上传并解析" }).click();
  await expect(page.getByRole("heading", { name: "Step 00 材料基线" })).toBeVisible();
  await page.getByRole("button", { name: "发布 Step 00 材料基线" }).click();

  await page.getByRole("tab", { name: "结构预览" }).click();
  await page.getByRole("button", { name: "创建结构分析运行" }).click();
  await page.getByRole("button", { name: "执行下一批" }).click();
  await expect(page.getByText("需求确认表")).toBeVisible();
  await page.getByRole("button", { name: "选择当前筛选结果" }).click();
  while (await page.locator(".requirement-summary details:not([open]) summary").count()) {
    await page.locator(".requirement-summary details:not([open]) summary").first().click();
  }
  while (await page.getByRole("button", { name: "标记已处理" }).count()) {
    const updated = page.waitForResponse((response) => response.request().method() === "PATCH"
      && response.url().includes("/findings/"));
    await page.getByRole("button", { name: "标记已处理" }).first().dispatchEvent("click");
    await updated;
  }
  while (await page.getByRole("button", { name: "以 SRS 为准" }).count()) {
    await page.getByRole("button", { name: "以 SRS 为准" }).first().click();
  }
  await page.getByRole("button", { name: "确认已选需求" }).click();

  await page.getByRole("tab", { name: "新增建议" }).click();
  await page.getByRole("button", { name: "生成新增建议" }).click();
  await expect(page.getByRole("button", { name: "拒绝" })).toHaveCount(4);
  while (await page.getByRole("button", { name: "拒绝" }).count()) {
    const updated = page.waitForResponse((response) => response.request().method() === "PATCH"
      && response.url().includes("/suggestions/"));
    await page.getByRole("button", { name: "拒绝" }).first().dispatchEvent("click");
    await updated;
  }

  await page.getByRole("tab", { name: "审核" }).click();
  await page.getByRole("button", { name: "生成测试点审核" }).click();
  const testItemSelection = page.locator(".workflow-panel input[type=checkbox]");
  await expect(testItemSelection).toHaveCount(5);
  await testItemSelection.first().check();
  await page.getByRole("button", { name: "确认审核并固化交接" }).click();

  await expect(page.getByRole("tab", { name: "测试用例" })).toBeEnabled();
  await page.getByRole("tab", { name: "测试用例" }).click();
  await page.getByRole("button", { name: "生成测试设计候选" }).click();
  await page.getByRole("button", { name: "确认测试设计" }).click();
  await page.getByRole("button", { name: "创建用例生成运行" }).click();
  await expect(page.getByRole("button", { name: "执行下一批" })).toBeVisible();
  await page.getByRole("button", { name: "执行下一批" }).click();
  await expect(page.getByRole("button", { name: "开始三角色 AI 评审" })).toBeVisible();
  await page.getByRole("button", { name: "开始三角色 AI 评审" }).click();
  await expect(page.getByRole("button", { name: "拒绝" })).not.toHaveCount(0);
  while (await page.getByRole("button", { name: "拒绝" }).count()) {
    const updated = page.waitForResponse((response) => response.request().method() === "PATCH"
      && response.url().includes("/suggestions/"));
    await page.getByRole("button", { name: "拒绝" }).first().dispatchEvent("click");
    await updated;
  }
  await page.getByRole("button", { name: "完成用例确认" }).click();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载用例文件" }).click();
  expect((await download).suggestedFilename()).toMatch(/standard-test-cases\.(xlsx|csv)/);
  await expect(page.getByRole("tab")).toHaveCount(5);
  await expect(page.getByText("高级治理与历史详情")).toBeVisible();
  await expect(page.getByText("资产来源记录")).toHaveCount(0);
});
