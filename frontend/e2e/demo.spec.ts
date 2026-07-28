import { expect, test } from "@playwright/test";

test("current workspace exposes the five-stage Python-backed workflow", async ({ page }) => {
  await page.goto("/data");
  await expect(page.getByText("HomeShift", { exact: true })).toBeVisible();
  await expect(page.getByText("数据接入", { exact: true })).toBeVisible();
  await expect(page.getByText("基线", { exact: true })).toBeVisible();
  await expect(page.getByText("诊断", { exact: true })).toBeVisible();
  await expect(page.getByText("计划", { exact: true })).toBeVisible();
  await expect(page.getByText("追踪与记忆", { exact: true })).toBeVisible();
});

test("locked stages explain the prerequisite instead of silently skipping", async ({ page }) => {
  await page.goto("/data");
  await page.getByRole("button", { name: "计划 locked" }).click();
  await expect(page).toHaveURL(/\/diagnosis$/);
  await expect(page.getByText(/计划阶段尚未解锁/)).toBeVisible();
  await expect(page.getByText("Agent 尚未开始本次诊断")).toBeVisible();
});

test("synthetic household completes diagnosis, proposal, commit, tracking and review", async ({ page }) => {
  await page.goto("/data");

  await page.getByRole("button", { name: /模型/ }).click();
  await page.getByRole("button", { name: /离线 Mock/ }).click();
  await page.getByRole("button", { name: "应用选择" }).click();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "导入并建立当前工作空间" }).click();
  await expect(page).toHaveURL(/\/baseline$/);
  await expect(page.getByText("合成演示数据", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: /诊断/ }).click();
  await page.route("**/api/v1/diagnose", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.continue();
  });
  await page.getByRole("button", { name: "运行本次 Agent 诊断" }).click();
  await expect(page.getByRole("status", { name: "AI 正在分析当前家庭数据" })).toBeVisible();
  await expect(page.getByText("ORCHESTRATOR MEMO", { exact: true })).toBeVisible();
  await expect(page.getByText("本次 Agent 诊断已完成")).toBeVisible();

  await page.getByRole("link", { name: /计划/ }).click();
  await expect(page.getByText("候选潜力已计算，Agent 尚未提案")).toBeVisible();
  await page.getByRole("button", { name: "让 Agent 提出建议" }).click();
  await expect(page.locator(".action-card.selected").first()).toBeVisible();
  await page.getByRole("button", { name: "确认并提交正式计划" }).click();
  await expect(page.getByText("COMMITTED PLAN / V1", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: /追踪与记忆/ }).click();
  await page.getByRole("button", { name: "生成合成实施后数据" }).click();
  await expect(page.getByText("当前追踪使用合成实施后数据", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "运行复盘 Agent" }).click();
  await expect(page.getByText(/周度复盘报告/)).toBeVisible();
});
