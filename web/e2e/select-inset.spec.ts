import { expect, test, type Locator } from "@playwright/test";

async function checkInset(select: Locator) {
  await expect(select).toBeVisible();
  const style = await select.evaluate((element) => {
    const computed = getComputedStyle(element);
    return {
      appearance: computed.appearance,
      position: computed.backgroundPosition,
      padding: computed.paddingInlineEnd,
    };
  });
  expect(style.appearance).toBe("none");
  expect(style.position).toBe("calc(100% - 12px) 50%");
  expect(style.padding).toBe("36px");
}

test("shared selects keep an inset chevron and native forced-colors fallback", async ({ page }) => {
  await page.goto("/datasets/deletion-target");
  await expect(page.getByRole("alert")).toBeVisible();
  await page.goto("/datasets");
  await page.locator("aside details.appearance summary").click();
  await checkInset(page.locator("aside").getByLabel("Theme"));
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await checkInset(page.getByLabel("Segment", { exact: true }));
  await page.getByRole("link", { name: "Output settings" }).click();
  await checkInset(page.getByLabel("Output format"));
  await page.screenshot({ path: "test-results/select-inset.png", fullPage: true });
  await page.emulateMedia({ forcedColors: "active" });
  const forced = await page.getByLabel("Output format").evaluate((element) => {
    const style = getComputedStyle(element);
    return { appearance: style.appearance, image: style.backgroundImage };
  });
  expect(forced).toEqual({ appearance: "auto", image: "none" });
});
