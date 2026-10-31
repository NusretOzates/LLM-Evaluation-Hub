import { expect, test } from "@playwright/test";

test.skip(process.env.WORKBENCH_TEST_ACCEPTANCE !== "1", "Requires the isolated multi-dataset acceptance fixture.");

test("multi-dataset name and match-all filters honor ancestry and unavailable tags", async ({ page }) => {
  await page.goto("/datasets?tag=Benchmarks");
  for (const name of ["Alpha", "Beta", "Gamma"])
    await expect(page.getByRole("link", { name, exact: true }).first()).toBeVisible();
  for (const name of ["Delta", "Boundary", "Trashed"])
    await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0);
  await page.goto("/datasets?tag=Benchmarks%2FReasoning&tag=Language%2FEnglish&q=ALP");
  await expect(page.getByRole("link", { name: "Alpha", exact: true }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Beta", exact: true })).toHaveCount(0);
  await page.getByRole("searchbox", { name: "Search datasets" }).fill("Beta");
  await expect(page.getByText("No matching datasets")).toBeVisible();
  await page.goto("/datasets?tag=Deleted&tag=Deleted&tag=");
  await expect(page.getByText("Deleted (Unavailable)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Deleted" })).toHaveCount(1);
  await expect(page.getByText("No matching datasets")).toBeVisible();
});

test("tag detail counts direct and distinct branch assignments", async ({ page }) => {
  await page.goto("/tags?selected=Benchmarks");
  await expect(page.getByText("Directly tagged: 1")).toBeVisible();
  await expect(page.getByText("In this branch: 3")).toBeVisible();
  await page.getByRole("button", { name: "Add sub-tag", exact: true }).click();
  await page.getByLabel("Tag name").fill("Math");
  await page.getByRole("button", { name: "Create tag" }).click();
  await expect(page).toHaveURL(/selected=Benchmarks%2FMath/);
  await expect(page.getByText("Directly tagged: 0")).toBeVisible();
  await expect(page.getByText("In this branch: 0")).toBeVisible();
});
