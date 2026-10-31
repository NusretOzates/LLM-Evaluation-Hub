import { expect, test } from "@playwright/test";

for (const initialTheme of ["light", "dark"] as const) {
  test(`processor keeps its document and undo history starting in ${initialTheme}`, async ({ page }) => {
    await page.addInitScript((theme) => localStorage.setItem("evaluation-hub.theme", theme), initialTheme);
    await page.setViewportSize({ width: 900, height: 900 });
    await page.route("**/api/dataset-source-samples", (route) =>
      route.fulfill({
        json: {
          id: "sample",
          source: { kind: "hf_dataset", repo_id: "fixtures/cases", config: null, split: "train", revision: "main" },
          resolved_sha: "synthetic",
          row_limit: 10000,
          rows: [{ text: "hello" }],
          columns: [{ name: "text", types: ["string"] }],
          expires_at: "2099-01-01T00:00:00Z",
        },
      }),
    );
    let previewRuns = 0;
    await page.route("**/api/dataset-previews", (route) => {
      previewRuns += 1;
      if (previewRuns === 2)
        return route.fulfill({
          json: {
            id: null,
            sample_id: "sample",
            resolved_sha: "synthetic",
            source_hash: "hash",
            rows_kept: 0,
            rows_dropped: 0,
            valid: false,
            expires_at: "2099-01-01T00:00:00Z",
            rows: [
              {
                source_index: 0,
                status: "failed",
                example: null,
                error: {
                  category: "processor",
                  message: "Example failure",
                  source_index: 0,
                  line: 2,
                  column: 1,
                  field_path: null,
                },
              },
            ],
          },
        });
      return route.fulfill({
        json: {
          id: "preview",
          sample_id: "sample",
          resolved_sha: "synthetic",
          source_hash: "hash",
          rows_kept: 1,
          rows_dropped: 0,
          valid: true,
          expires_at: "2099-01-01T00:00:00Z",
          rows: [
            {
              source_index: 0,
              status: "kept",
              error: null,
              example: {
                conversation: [{ role: "user", content: "hello" }],
                tools: [],
                expected_output: null,
                extras: {},
                segments: {},
              },
            },
          ],
        },
      });
    });
    await page.goto("/dataset-imports/new");
    await page.getByLabel("Dataset name").fill("theme-test");
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.getByLabel("Dataset repository").fill("fixtures/cases");
    await page.getByRole("button", { name: "Load sample" }).click();
    await expect(page.getByText(/1 sample rows/)).toBeVisible();
    await page.getByRole("checkbox", { name: "text", exact: true }).check();
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    const editor = page.locator(".cm-content");
    await expect(editor).toContainText('"text": str(row["text"])');
    await editor.focus();
    await page.keyboard.press("ControlOrMeta+End");
    await page.keyboard.type("\n# test");
    const document = await editor.textContent();
    await page.getByText("Replace with a starter template").click();
    await page.getByRole("button", { name: "No tools", exact: true }).click();
    const replaceDialog = page.getByRole("dialog", { name: "Replace processor code?" });
    await expect(replaceDialog.getByRole("button", { name: "Cancel" })).toBeFocused();
    await replaceDialog.getByRole("button", { name: "Cancel" }).click();
    expect(await editor.textContent()).toBe(document);
    await editor.focus();
    await page.keyboard.press("ControlOrMeta+End");
    await page.keyboard.press("Shift+Home");
    const selection = await page.evaluate(() => window.getSelection()?.toString());
    expect(selection).toBe("# test");
    await page.getByRole("button", { name: "Run preview" }).click();
    await expect(page.getByRole("button", { name: "Continue to review" })).toBeEnabled();
    await page.locator("aside").getByLabel("Appearance").click();
    await page
      .locator("aside")
      .getByLabel("Theme")
      .selectOption(initialTheme === "light" ? "dark" : "light");
    await expect(page.getByRole("button", { name: "Continue to review" })).toBeEnabled();
    await page.getByRole("button", { name: "Input", exact: true }).click();
    await page.getByRole("button", { name: "Processor", exact: true }).click();
    expect(await editor.textContent()).toBe(document);
    await editor.focus();
    await page.waitForTimeout(100);
    expect(await page.evaluate(() => window.getSelection()?.toString())).toBe(selection);
    await page.keyboard.press("ControlOrMeta+z");
    await expect(editor).not.toContainText("# test");
    await page.getByRole("button", { name: "Run preview" }).click();
    await expect(page.locator(".cm-processor-error-line")).toHaveCount(1);
    await page.locator("aside").getByLabel("Theme").selectOption(initialTheme);
    await expect(page.locator(".cm-processor-error-line")).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "Preview rows" })).toBeFocused();
    await page.getByRole("button", { name: "Run preview" }).click();
    await page.getByRole("button", { name: "Continue to review" }).click();
    await expect(page.getByRole("heading", { name: "Review import" })).toBeVisible();
    await expect(page.getByText("fixtures/cases").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Import dataset" })).toBeEnabled();
  });
}

test("expired samples cannot advance and source values remain available", async ({ page }) => {
  await page.route("**/api/dataset-source-samples", (route) =>
    route.fulfill({
      json: {
        id: "expired",
        source: { kind: "hf_dataset", repo_id: "fixtures/cases", config: "custom", split: "train", revision: "main" },
        resolved_sha: "pinned",
        row_limit: 20,
        rows: [{ text: "hello" }],
        columns: [{ name: "text", types: ["string"] }],
        expires_at: "2020-01-01T00:00:00Z",
      },
    }),
  );
  await page.goto("/dataset-imports/new");
  await page.getByLabel("Dataset name").fill("expired-fixture");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Dataset repository").fill("fixtures/cases");
  await page.getByText("Advanced source settings", { exact: false }).click();
  await page.getByLabel("Config").fill("custom");
  await page.getByLabel("Source-row limit").fill("20");
  await page.getByRole("button", { name: "Load sample" }).click();
  await expect(page.getByText(/resolved to pinned/)).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Load a source sample");
  await expect(page.getByLabel("Config")).toHaveValue("custom");
  await expect(page.getByLabel("Source-row limit")).toHaveValue("20");
});
