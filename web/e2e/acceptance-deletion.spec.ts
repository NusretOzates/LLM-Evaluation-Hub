import { expect, test } from "@playwright/test";

test.skip(process.env.WORKBENCH_TEST_ACCEPTANCE !== "1", "Requires the isolated multi-dataset acceptance fixture.");
test.describe.configure({ mode: "serial" });

type Dataset = { id: string; name: string; tags: string[] };
async function datasets(request: import("@playwright/test").APIRequestContext): Promise<Dataset[]> {
  return (await request.get("/api/datasets")).json();
}

test("promotion removes direct assignment and retains child assignments", async ({ page, request }) => {
  const before = await datasets(request);
  expect((await request.post("/api/tags", { data: { Reasoning: { children: {} } } })).ok()).toBeTruthy();
  await page.goto("/tags?selected=Benchmarks");
  await page.getByRole("button", { name: "Actions for tag Benchmarks" }).click();
  await page.getByRole("menuitem", { name: "Delete grouping and keep sub-tags" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  expect((await datasets(request)).map((item) => item.tags)).toEqual(before.map((item) => item.tags));
  await dialog.getByRole("button", { name: "Cancel" }).click();
  expect(
    (await request.post("/api/tag-deletion", { data: { path: "Reasoning", promote_children: false } })).ok(),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Actions for tag Benchmarks" }).click();
  await page.getByRole("menuitem", { name: "Delete grouping and keep sub-tags" }).click();
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page).toHaveURL(/\/tags$/);
  const after = await datasets(request);
  expect(after.find((item) => item.name === "Alpha")?.tags).toContain("Reasoning");
  expect(after.find((item) => item.name === "Beta")?.tags).toContain("Tool use");
  expect(after.find((item) => item.name === "Gamma")?.tags).not.toContain("Benchmarks");
  expect(after.map((item) => item.id)).toEqual(before.map((item) => item.id));
});

test("subtree deletion removes assignments without deleting datasets", async ({ page, request }) => {
  expect(
    (
      await request.post("/api/tags", {
        data: { Benchmarks: { children: { Reasoning: { children: {} }, "Tool use": { children: {} } } } },
      })
    ).ok(),
  ).toBeTruthy();
  const before = await datasets(request);
  for (const [name, path] of [
    ["Alpha", "Benchmarks/Reasoning"],
    ["Beta", "Benchmarks/Tool use"],
    ["Gamma", "Benchmarks"],
  ]) {
    const item = before.find((entry) => entry.name === name);
    expect(item).toBeDefined();
    expect((await request.post(`/api/dataset-ids/${item?.id}/tags`, { data: { paths: [path] } })).ok()).toBeTruthy();
  }
  await page.goto("/tags?selected=Benchmarks");
  await page.getByRole("button", { name: "Actions for tag Benchmarks" }).click();
  await page.getByRole("menuitem", { name: "Delete tag and sub-tags" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page).toHaveURL(/\/tags$/);
  const after = await datasets(request);
  expect(after.map((item) => item.id)).toEqual(before.map((item) => item.id));
  for (const name of ["Alpha", "Beta", "Gamma"])
    expect(
      after
        .find((item) => item.name === name)
        ?.tags.some((tag) => tag === "Benchmarks" || tag.startsWith("Benchmarks/")),
    ).toBe(false);
});
