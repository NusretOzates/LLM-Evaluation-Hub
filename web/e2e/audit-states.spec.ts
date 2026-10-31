import { expect, test } from "@playwright/test";

for (const theme of ["light", "dark"] as const) {
  test(`catalog loading, failure and empty states in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("evaluation-hub.theme", value), theme);
    let release = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/datasets", async (route) => {
      await gate;
      await route.fulfill({ json: [] });
    });
    await page.route("**/api/tags", (route) => route.fulfill({ json: {} }));
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await expect(page.locator('.shell[aria-busy="true"]')).toBeVisible();
    await expect(page.getByRole("heading", { name: "No datasets yet" })).toHaveCount(0);
    release();
    await expect(page.getByRole("heading", { name: "No datasets yet" })).toBeVisible();
    await page.unrouteAll({ behavior: "wait" });
    await page.route("**/api/tags", (route) => route.fulfill({ status: 500, json: { detail: "Catalog unavailable" } }));
    await page.reload();
    await expect(page.getByRole("heading", { name: "Catalog unavailable" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "No datasets yet" })).toHaveCount(0);
  });
}
