import { expect, test } from "@playwright/test";

test("select hierarchical tags and choose a parent when creating a tag", async ({ page, request }) => {
  const created = await request.post("/api/tags", {
    data: { "QA Benchmarks": { children: { Reasoning: {}, "Tool use": {} } } },
  });
  expect(created.ok()).toBeTruthy();
  await page.goto("/dataset-imports/new");
  const picker = page.locator(".tag-picker");
  await picker.getByRole("checkbox", { name: "QA Benchmarks", exact: true }).check();
  await picker.getByRole("checkbox", { name: "QA Benchmarks/Reasoning", exact: true }).check();
  await expect(picker.getByRole("checkbox", { name: "QA Benchmarks", exact: true })).not.toBeChecked();
  await expect(picker.getByText("Included through child")).toBeVisible();
  await picker.getByRole("checkbox", { name: "QA Benchmarks/Tool use", exact: true }).check();
  await picker.getByRole("textbox", { name: "Search tags", exact: true }).fill("Reasoning");
  await expect(picker.getByRole("checkbox", { name: "QA Benchmarks", exact: true })).toBeVisible();
  await expect(picker.getByRole("checkbox", { name: "QA Benchmarks/Tool use", exact: true })).toHaveCount(0);
  await picker.getByRole("textbox", { name: "Search tags", exact: true }).fill("");
  await page.screenshot({ path: "/tmp/tag-selector.png", fullPage: true });
  await page.goto("/tags?selected=QA+Benchmarks");
  await page.getByRole("button", { name: "Add sub-tag", exact: true }).click();
  const creator = page.getByRole("dialog", { name: "Add sub-tag" });
  await expect(creator.getByText("Parent: QA Benchmarks")).toBeVisible();
  await creator.getByRole("textbox", { name: "Tag name", exact: true }).fill("Math");
  await creator.getByRole("button", { name: "Create tag", exact: true }).click();
  await expect(page).toHaveURL(/selected=QA\+Benchmarks%2FMath/);
  await expect(page.getByRole("heading", { name: "Math", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "New tag", exact: true }).click();
  const newTag = page.getByRole("dialog", { name: "New tag" });
  await expect(newTag.getByText("Parent: Top level")).toBeVisible();
  await newTag.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(newTag).toBeHidden();
});
