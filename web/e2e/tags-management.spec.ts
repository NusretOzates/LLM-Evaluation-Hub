import { expect, test } from "@playwright/test";

test("tag promotion reports collisions and succeeds after resolving them", async ({ page, request }) => {
  expect(
    (
      await request.post("/api/tags", {
        data: { PromoteFixture: { children: { SharedFixture: { children: {} } } }, SharedFixture: { children: {} } },
      })
    ).ok(),
  ).toBeTruthy();
  await page.goto("/tags?selected=PromoteFixture");
  await page.getByRole("button", { name: "Actions for tag PromoteFixture" }).click();
  await page.getByRole("menuitem", { name: "Delete grouping and keep sub-tags" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  expect(
    (await request.post("/api/tag-deletion", { data: { path: "SharedFixture", promote_children: false } })).ok(),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Actions for tag PromoteFixture" }).click();
  await page.getByRole("menuitem", { name: "Delete grouping and keep sub-tags" }).click();
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page).toHaveURL(/\/tags$/);
  await expect(page.getByRole("button", { name: "SharedFixture", exact: true })).toBeVisible();
});

test("subtree deletion removes labels and retains the catalog", async ({ page, request }) => {
  const before = (await (await request.get("/api/datasets")).json()) as Array<{ id: string }>;
  expect(before.length).toBeGreaterThan(0);
  expect(
    (await request.post("/api/tags", { data: { DeleteFixture: { children: { Child: { children: {} } } } } })).ok(),
  ).toBeTruthy();
  await page.goto("/tags?selected=DeleteFixture");
  await page.getByRole("button", { name: "Actions for tag DeleteFixture" }).click();
  await page.getByRole("menuitem", { name: "Delete tag and sub-tags" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page).toHaveURL(/\/tags$/);
  await expect(page.getByRole("button", { name: "DeleteFixture", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Tags", exact: true })).toBeFocused();
  const after = (await (await request.get("/api/datasets")).json()) as Array<{ id: string }>;
  expect(after.map((dataset) => dataset.id)).toEqual(before.map((dataset) => dataset.id));
});

test("creating a child selects it and View datasets opens its filter", async ({ page }) => {
  await page.goto("/tags?selected=Browser");
  await page.getByRole("button", { name: "Add sub-tag", exact: true }).click();
  await expect(page.getByLabel("Tag name")).toBeFocused();
  await page.getByLabel("Tag name").fill("Math");
  await page.getByRole("button", { name: "Create tag" }).click();
  await expect(page).toHaveURL(/selected=Browser%2FMath/);
  await expect(page.getByRole("heading", { name: "Math", exact: true })).toBeVisible();
  await expect(page.locator('[data-tag-path="Browser/Math"]')).toBeFocused();
  await page.getByRole("link", { name: "View datasets" }).click();
  await expect(page).toHaveURL(/tag=Browser%2FMath/);
});

test("pending tag mutations cannot be dismissed", async ({ page }) => {
  let releaseCreate = () => {};
  const createGate = new Promise<void>((resolve) => {
    releaseCreate = resolve;
  });
  await page.route("**/api/tags", async (route) => {
    if (route.request().method() === "POST") await createGate;
    await route.continue();
  });
  await page.goto("/tags");
  await page.getByRole("button", { name: "New tag", exact: true }).click();
  await page.getByLabel("Tag name").fill("PendingFixture");
  await page.getByRole("button", { name: "Create tag" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  releaseCreate();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(/selected=PendingFixture/);
  let releaseDelete = () => {};
  const deleteGate = new Promise<void>((resolve) => {
    releaseDelete = resolve;
  });
  await page.route("**/api/tag-deletion", async (route) => {
    await deleteGate;
    await route.continue();
  });
  await page.getByRole("button", { name: "Actions for tag PendingFixture" }).click();
  await page.getByRole("menuitem", { name: "Delete tag and sub-tags" }).click();
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  releaseDelete();
  await expect(dialog).toBeHidden();
});
