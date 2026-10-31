import { expect, test } from "@playwright/test";

test("system theme follows changes, explicit preference survives reload", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.addInitScript(() => {
    requestAnimationFrame(() => {
      document.documentElement.dataset.firstFrameTheme = document.documentElement.dataset.theme;
    });
  });
  await page.goto("/datasets");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-first-frame-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.locator("aside").getByLabel("Appearance").click();
  await page.locator("aside").getByLabel("Theme").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("narrow navigation closes on Escape and restores focus", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 850 });
  await page.goto("/datasets");
  const menu = page.getByRole("button", { name: "Menu", exact: true });
  await menu.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(menu).toBeFocused();
});

test("action menu supports keyboard navigation and returns focus on Escape", async ({ page }) => {
  await page.goto("/datasets");
  const trigger = page.getByRole("button", { name: "Actions for team/cases %?#" });
  await trigger.click();
  await expect(page.getByRole("menuitem", { name: "Move to Trash" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Move to Trash" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

for (const initial of ["light", "dark"] as const) {
  test(`first frame follows ${initial} system theme`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: initial });
    await page.addInitScript(() => {
      requestAnimationFrame(() => {
        document.documentElement.dataset.firstFrameTheme = document.documentElement.dataset.theme;
      });
    });
    await page.goto("/datasets");
    await expect(page.locator("html")).toHaveAttribute("data-first-frame-theme", initial);
    await expect(page.locator("html")).toHaveAttribute("data-theme", initial);
  });
}

for (const preference of ["light", "dark"] as const) {
  test(`explicit ${preference} preference survives reload and system changes`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: preference === "light" ? "dark" : "light" });
    await page.goto("/datasets");
    await page.locator("aside").getByLabel("Appearance").click();
    await page.locator("aside").getByLabel("Theme").selectOption(preference);
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", preference);
    await page.emulateMedia({ colorScheme: preference });
    await page.emulateMedia({ colorScheme: preference === "light" ? "dark" : "light" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", preference);
  });
}
