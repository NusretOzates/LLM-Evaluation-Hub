import { expect, test } from "@playwright/test";

test("evaluate saved predictions and inspect coverage", async ({ page }) => {
  await page.goto("/evaluations/new");
  await page.getByRole("combobox", { name: "Run" }).selectOption("evaluation-demo");
  await page.getByLabel(/Evaluation demo · 10 selected rows/).check();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Test method" }).click();
  await expect(page.getByRole("button", { name: "Test scoring" })).toBeEnabled({ timeout: 10000 });
  await page.getByRole("button", { name: "Test scoring" }).click();
  await expect(page.getByText("correctness", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Run evaluation" }).click();
  await expect(page.getByText("10 / 10 rows processed")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/10 \/ 10 \(100%\)/)).toBeVisible();
  await page.getByLabel("Group by").selectOption("dataset");
  await expect(page.getByRole("cell", { name: "Evaluation demo" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Delete evaluation?" });
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await dialog.getByRole("button", { name: "Delete evaluation" }).click();
  await expect(page).toHaveURL(/\/evaluations$/);
});
