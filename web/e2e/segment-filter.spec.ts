import { expect, test } from "@playwright/test";

for (const theme of ["light", "dark"] as const) {
  test(`segment value filtering supports many values and resets on key changes in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("evaluation-hub.theme", value), theme);
    await page.route("**/api/dataset-ids/*/examples?*", (route) =>
      route.fulfill({
        json: {
          total: 12,
          offset: 0,
          limit: 50,
          examples: Array.from({ length: 12 }, (_, index) => ({
            conversation: [{ role: "user", content: `Example language ${index}` }],
            expected_output: null,
            extras: {},
            tools: [],
            segments: { language: `Language ${index}`, source: "Same source", blank: "" },
          })),
        },
      }),
    );
    await page.goto("/datasets");
    await page.getByRole("link", { name: "team/cases %?#", exact: true }).click();
    await page.getByLabel("Segment", { exact: true }).selectOption("language");
    const value = page.getByLabel("Segment value", { exact: true });
    await expect(value.locator("option")).toHaveCount(13);
    await value.selectOption({ label: "Language 9" });
    await expect(page.locator(".row-items .row-item")).toHaveCount(1);
    await expect(page.locator(".row-items")).toContainText("Example language 9");
    await page.screenshot({ path: `/tmp/segment-filter-${theme}.png`, fullPage: true });
    await page.getByLabel("Segment", { exact: true }).selectOption("source");
    await expect(value).toHaveValue("all");
    await value.selectOption({ label: "Same source" });
    await expect(page.locator(".row-items .row-item")).toHaveCount(12);
    await page.getByLabel("Segment", { exact: true }).selectOption("blank");
    await value.selectOption({ label: "(Empty value)" });
    await expect(value).toHaveValue("value:");
    await expect(page.locator(".row-items .row-item")).toHaveCount(12);
    await value.selectOption("all");
    await expect(value).toHaveValue("all");
    await page.setViewportSize({ width: 375, height: 900 });
    await page.getByRole("button", { name: "Row list", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Examples", exact: true }).getByLabel("Segment value")).toBeVisible();
  });
}
