import { expect, test } from "@playwright/test";

test("tag and dataset deletion menus preserve filtering and support recovery", async ({ page }) => {
  await page.goto("/tags?selected=Browser");
  await page.getByRole("button", { name: "Actions for tag Browser" }).click();
  await page.getByRole("menuitem", { name: "Delete tag and sub-tags" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(page).toHaveURL(/selected=Browser/);
  await page.goto("/datasets");
  await page.getByRole("button", { name: "Actions for team/cases %?#", exact: true }).click();
  await page.screenshot({ path: "/tmp/dataset-menu-fixed.png", fullPage: true });
  await page.getByRole("menuitem", { name: "Move to Trash" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("link", { name: "team/cases %?#" })).toBeVisible();
  await page.getByRole("button", { name: "Actions for team/cases %?#", exact: true }).click();
  await page.getByRole("menuitem", { name: "Move to Trash" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Move to Trash" }).click();
  await expect(page.getByRole("link", { name: "team/cases %?#" })).toHaveCount(0);
  await page.getByRole("link", { name: "Trash", exact: true }).click();
  await page.getByRole("button", { name: "Restore" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await page.locator('aside a[href="/datasets"]').click();
  await page.getByRole("button", { name: "Actions for deletion-target", exact: true }).click();
  await page.getByRole("menuitem", { name: "Move to Trash" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Move to Trash" }).click();
  await page.getByRole("link", { name: "Trash", exact: true }).click();
  await page.getByRole("button", { name: "Delete permanently" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete permanently" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
});

test("a pending Trash move cannot be dismissed", async ({ page }) => {
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/trash/*", async (route) => {
    if (route.request().method() === "POST") await gate;
    await route.continue();
  });
  await page.goto("/datasets");
  await page.getByRole("button", { name: "Actions for team/cases %?#" }).click();
  await page.getByRole("menuitem", { name: "Move to Trash" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Move to Trash" }).click();
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  release();
  await expect(dialog).toBeHidden();
  await page.getByRole("link", { name: "Trash", exact: true }).click();
  await page.getByRole("button", { name: "Restore" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
});
