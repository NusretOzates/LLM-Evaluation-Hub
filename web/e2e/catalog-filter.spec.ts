import { expect, test } from "@playwright/test";

test("filter changes preserve URL history and normalize interactive selections", async ({ page, request }) => {
  const response = await request.post("/api/tags", {
    data: { FilterFixture: { children: { Alpha: { children: {} }, Beta: { children: {} } } } },
  });
  expect(response.ok()).toBeTruthy();
  await page.goto("/datasets?extra=kept");
  await page.getByRole("button", { name: "Tags", exact: true }).click();
  await page.getByRole("checkbox", { name: "FilterFixture", exact: true }).click();
  await expect(page).toHaveURL(/tag=FilterFixture/);
  await page.getByRole("checkbox", { name: "FilterFixture/Alpha", exact: true }).click();
  await expect(page).toHaveURL(/tag=FilterFixture%2FAlpha/);
  await expect(page.getByRole("button", { name: "Remove FilterFixture", exact: true })).toHaveCount(0);
  await page.getByRole("checkbox", { name: "FilterFixture/Beta", exact: true }).click();
  await expect(page).toHaveURL(/tag=FilterFixture%2FAlpha.*tag=FilterFixture%2FBeta/);
  await page.goBack();
  await expect(page).toHaveURL(/tag=FilterFixture%2FAlpha/);
  await expect(page.getByRole("button", { name: "Remove FilterFixture/Beta" })).toHaveCount(0);
  await page.goForward();
  await expect(page.getByRole("button", { name: "Remove FilterFixture/Beta" })).toBeVisible();
  await page.goBack();
  await page.reload();
  await expect(page.getByRole("button", { name: "Remove FilterFixture/Alpha" })).toBeVisible();
  await page.locator(".filter-token summary").filter({ hasText: "FilterFixture/Alpha" }).click();
  await expect(page.locator(".filter-token details[open]")).toBeVisible();
  await page.getByLabel("Search datasets").fill("ALP");
  await expect(page).toHaveURL(/q=ALP/);
  await page.getByRole("button", { name: "Clear filters" }).first().click();
  await expect(page).toHaveURL(/extra=kept/);
  expect(new URL(page.url()).searchParams.has("tag")).toBe(false);
  expect(new URL(page.url()).searchParams.has("q")).toBe(false);
});

test("scrolling a long filter tree keeps its popover open", async ({ page, request }) => {
  const children = Object.fromEntries(Array.from({ length: 25 }, (_, index) => [`Node${index}`, { children: {} }]));
  expect((await request.post("/api/tags", { data: { LongTreeFixture: { children } } })).ok()).toBeTruthy();
  await page.goto("/datasets");
  await page.getByRole("button", { name: "Tags", exact: true }).click();
  const panel = page.locator(".catalog-filter-panel");
  await expect(panel).toHaveAttribute("data-positioned", "true");
  const trigger = await page.getByRole("button", { name: "Tags", exact: true }).boundingBox();
  const bounds = await panel.boundingBox();
  expect(bounds?.x).toBeCloseTo(trigger?.x ?? 0, 0);
  const options = page.locator(".hierarchy-options");
  await options.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(page.getByRole("checkbox", { name: "LongTreeFixture/Node9" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tags", exact: true })).toHaveAttribute("aria-expanded", "true");
});
