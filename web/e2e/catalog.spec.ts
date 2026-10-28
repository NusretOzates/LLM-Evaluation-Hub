import { expect, test } from "@playwright/test";

test("browse a real catalog, retain special tags, reset page facets and mutate links", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) requests.push(request.url());
  });
  await page.goto("/datasets");
  await expect(page.getByRole("link", { name: "__proto__ 0" })).toBeVisible();
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await expect(page.getByRole("heading", { name: "team/cases %?#", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/datasets\/[0-9a-f-]{36}$/);
  await page.getByRole("button", { name: "a", exact: true }).click();
  await page.getByRole("link", { name: "Next page" }).click();
  await expect(page.getByText("Synthetic row 51", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("No rows on this page match.")).toHaveCount(0);
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/row=52/);
  await expect(page.getByRole("heading", { name: "Row 52 of 61" })).toBeVisible();
  const requestsBeforeSelection = requests.length;
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/row=53/);
  await expect(page.getByRole("heading", { name: "Row 53 of 61" })).toBeVisible();
  expect(requests.length).toBe(requestsBeforeSelection);
  await page.keyboard.press("k");
  await expect(page).toHaveURL(/row=52/);
  await page.getByRole("button", { name: "Dataset details" }).click();
  await page.getByLabel("Tag to add").selectOption("__proto__");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("button", { name: "Remove __proto__" })).toBeVisible();
  await page.getByRole("button", { name: "Remove __proto__" }).click();
  await expect(page.getByRole("button", { name: "Remove __proto__" })).toHaveCount(0);
  await page.getByRole("button", { name: "JSON", exact: true }).click();
  await expect(page.locator("pre.raw")).toContainText('"conversation"');
  expect(errors).toEqual([]);
});

test("blocked preferences and clipboard leave browsing usable", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get: () => {
        throw new Error("Storage denied");
      },
    });
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: () => Promise.reject(new Error("Clipboard denied")) },
    });
  });
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await page.getByRole("button", { name: "Copy", exact: true }).click();
  await expect(page.getByRole("button", { name: "Copy failed" })).toBeVisible();
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/row=2/);
});

for (const width of [1440, 1100, 768]) {
  test(`inspector remains usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/datasets");
    await page.getByRole("link", { name: "team/cases %?#" }).click();
    await expect(page.getByRole("heading", { name: /^Row / })).toBeVisible();
    await page.getByRole("button", { name: "Next row", exact: true }).click();
    await expect(page).toHaveURL(/row=2/);
    await page.screenshot({ path: `test-results/inspector-${width}.png`, fullPage: true });
  });
}

test("direct links cross row-page boundaries, preserve history and show URL errors", async ({ page }) => {
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await expect(page).toHaveURL(/\/datasets\/[0-9a-f-]{36}$/);
  const detail = new URL(page.url()).pathname;
  await page.goto(`${detail}?row=50`);
  await expect(page.getByRole("heading", { name: "Row 50 of 61" })).toBeVisible();
  await page.keyboard.press("j");
  await expect(page.getByRole("heading", { name: "Row 51 of 61" })).toBeVisible();
  await expect(page).toHaveURL(/offset=50&row=51/);
  await page.keyboard.press("k");
  await expect(page.getByRole("heading", { name: "Row 50 of 61" })).toBeVisible();
  await page.getByRole("link", { name: "Datasets", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Datasets", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Row 50 of 61" })).toBeVisible();
  await page.goto(`${detail}?row=9007199254740992`);
  await expect(page.getByRole("alert")).toContainText("safe whole number");
  await page.goto(`${detail}?offset=9999`);
  await expect(page.getByText("This page is past the last row.", { exact: false })).toBeVisible();
  await page.goto("/datasets/not-a-dataset");
  await expect(page.getByRole("alert")).toContainText("unknown dataset");
});
