import { expect, test } from "@playwright/test";

test.setTimeout(120_000);

test("从本地解析、范围勾选到用例编辑导出并可刷新恢复", async ({ page }) => {
  const projectName = `v0.2 浏览器验收项目 ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("button", { name: "新建测试设计项目" }).click();
  await page.getByLabel("项目名称").fill(projectName);
  await page.getByLabel("测试对象").fill("受控智能设备");
  await page.getByLabel("软件版本").fill("v0.2.0");
  await page.getByRole("button", { name: "创建并进入工作台" }).click();

  await expect(page.getByText("本页面不调用 AI")).toBeVisible();
  await page.getByLabel("补充说明（可选）").fill("重点关注状态变化和异常提示。");
  await page.getByLabel("需求文件").setInputFiles({
    name: "controlled-requirements.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# 状态管理\n设备必须返回当前状态。\n状态变化时必须记录时间戳。"),
  });
  await page.getByRole("button", { name: "上传并解析" }).click();
  await expect(page.getByText("解析成功")).toBeVisible();

  await page.getByRole("tab", { name: /需求分析/ }).click();
  await page.getByRole("button", { name: "开始需求分析" }).click();
  await expect(page.getByText("运行状态：已完成")).toBeVisible();
  const analysisRows = page.locator(".workspace-main tbody input[type=checkbox]");
  await expect(analysisRows).not.toHaveCount(0);
  await analysisRows.first().check();
  await expect(page.getByText(/已选 1 项，这些内容将用于生成测试用例/)).toBeVisible();

  await page.getByRole("tab", { name: /新增建议/ }).click();
  await page.getByRole("button", { name: "AI 分析新增建议" }).click();
  await expect(page.getByRole("button", { name: "接纳并回流" })).toBeVisible();
  await page.getByRole("button", { name: "接纳并回流" }).click();

  await page.getByRole("tab", { name: /审核/ }).click();
  await page.getByRole("button", { name: "跳过审核，进入测试用例" }).click();
  await expect(page.getByText("1. 测试用例模板")).toBeVisible();
  await expect(page.getByText(/默认测试用例模板.xlsx/)).toBeVisible();
  await page.getByLabel("4. 补充生成要求（可选）").fill("优先生成 P1 用例。");
  await page.getByRole("button", { name: "生成测试用例" }).click();
  await expect(page.getByText("运行状态：已完成")).toBeVisible();
  await expect(page.getByText(/正常与可观察结果/)).toBeVisible();

  await page.getByRole("button", { name: "编辑" }).first().click();
  await page.getByRole("dialog", { name: "编辑候选测试用例" }).getByLabel("标题").fill("人工确认后的状态用例");
  await page.getByRole("button", { name: "保存编辑" }).click();
  await expect(page.getByText("人工确认后的状态用例")).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 JSON" }).click();
  expect((await download).suggestedFilename()).toMatch(/cases-result\.json/);

  await page.reload();
  await page.getByRole("tab", { name: /测试用例/ }).click();
  await expect(page.getByText("人工确认后的状态用例")).toBeVisible();
  await expect(page.getByText(/已选 1 个测试点/)).toBeVisible();
  await expect(page.getByRole("tab")).toHaveCount(5);
  await expect(page.getByText(/批次/)).toHaveCount(0);
});
