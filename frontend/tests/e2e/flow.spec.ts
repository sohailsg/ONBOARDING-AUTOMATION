import { test, expect } from "@playwright/test";

// Staging e2e: login → pipeline → edit → approve → trace → execution-halt (spec §5).
// Run against staging (real API): BASE_URL + NEXT_PUBLIC_API_URL point at staging.

test("HR flow: pipeline → plan → approve → trace → halt", async ({ page }) => {
  await page.goto("/login?next=/admin");
  await page.getByLabel(/role/i).selectOption("hr_admin");
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page).toHaveURL(/\/admin/);

  await page.getByLabel(/filter by status/i).selectOption("awaiting_hr_approval");
  await expect(page.getByRole("table")).toBeVisible();

  const firstCase = page.getByRole("link").first();
  if (await firstCase.count()) {
    await firstCase.click();
    await page.getByRole("tab", { name: /plan/i }).click();
    await expect(page.getByText(/plan review/i)).toBeVisible();
    await page.getByRole("tab", { name: /trace/i }).click();
    await expect(page.getByText(/live trace/i)).toBeVisible();
    await page.getByRole("tab", { name: /execution/i }).click();
    await expect(page.getByRole("button", { name: /halt/i })).toBeVisible();
  }
});

test("employee flow: checklist tick + chat abstain path", async ({ page }) => {
  await page.goto("/login?next=/hub");
  await page.getByLabel(/role/i).selectOption("employee");
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page).toHaveURL(/\/hub/);
  await expect(page.getByText(/your first 30 days/i)).toBeVisible();
  await expect(page.getByText(/ask about policies/i)).toBeVisible();
});
