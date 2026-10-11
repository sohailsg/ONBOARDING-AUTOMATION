import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// 06-impl 6.7: WCAG AA gate on the two primary routes (mocked API via MSW,
// same webServer as flow.spec.ts). Fails on serious/critical violations.

async function loginAs(page: Page, role: "employee" | "hr_admin", next: string) {
  await page.goto(`/login?next=${next}`);
  await page.getByLabel(/role/i).selectOption(role);
  await page.getByRole("button", { name: /continue/i }).click();
}

for (const [name, role, path] of [
  ["hub", "employee", "/hub"],
  ["admin", "hr_admin", "/admin"],
] as const) {
  test(`a11y: ${name} has no serious violations`, async ({ page }) => {
    await loginAs(page, role, path);
    await expect(page.locator("#main")).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const blocking = results.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact ?? ""),
    );
    expect(
      blocking.map((v) => `${v.id}: ${v.description}`),
      "serious/critical a11y violations",
    ).toEqual([]);
  });
}
