import { expect, test } from "@playwright/test";

for (const theme of ["light", "dark"] as const) {
  test(`modal focus and containment in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("evaluation-hub.theme", value), theme);
    await page.goto("/tags");
    const create = page.getByRole("button", { name: "New tag", exact: true }).first();
    await create.click();
    const creation = page.getByRole("dialog", { name: "New tag" });
    await expect(page.getByLabel("Tag name")).toBeFocused();
    for (let index = 0; index < 8; index++) {
      await page.keyboard.press("Tab");
      expect(await creation.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(create).toBeFocused();
    await page.setViewportSize({ width: 375, height: 900 });
    await page.goto("/datasets");
    const filter = page.getByRole("button", { name: "Tags", exact: true });
    await filter.click();
    const filterSheet = page.getByRole("dialog", { name: "Filter by tags" });
    for (let index = 0; index < 8; index++) {
      await page.keyboard.press("Tab");
      expect(await filterSheet.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(filter).toBeFocused();
    await page.goto("/datasets");
    await page.getByRole("link", { name: "Alpha", exact: true }).click();
    const examples = page.getByRole("button", { name: "Row list" });
    await examples.click();
    const exampleSheet = page.getByRole("dialog", { name: "Examples" });
    for (let index = 0; index < 8; index++) {
      await page.keyboard.press("Tab");
      expect(await exampleSheet.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(examples).toBeFocused();
    await page.goto("/trash");
    const remove = page.getByRole("button", { name: "Delete permanently", exact: true }).first();
    await remove.click();
    const confirmation = page.getByRole("dialog");
    await expect(confirmation.getByRole("button", { name: "Cancel" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(remove).toBeFocused();
  });
}

for (const theme of ["light", "dark"] as const) {
  test(`pending tag creation remains modal in ${theme}`, async ({ page }) => {
    let release = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.addInitScript((value) => localStorage.setItem("evaluation-hub.theme", value), theme);
    await page.route("**/api/tags", async (route) => {
      if (route.request().method() === "POST") {
        await gate;
        await route.abort();
      } else await route.continue();
    });
    await page.goto("/tags");
    await page.getByRole("button", { name: "New tag", exact: true }).first().click();
    const dialog = page.getByRole("dialog", { name: "New tag" });
    await page.getByLabel("Tag name").fill(`Pending ${theme}`);
    await page.getByRole("button", { name: "Create tag" }).click();
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
    release();
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeEnabled();
    await dialog.getByRole("button", { name: "Cancel" }).click();
  });
}
