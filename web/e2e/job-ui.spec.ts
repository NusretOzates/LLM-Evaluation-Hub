import { expect, test } from "@playwright/test";

const job = {
  id: "ui-job",
  name: "Example import",
  state: "running",
  phase: "Processing",
  rows_loaded: 4,
  rows_kept: 3,
  rows_dropped: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  dataset_id: null,
  error: null,
  spec: {
    source: { kind: "hf_dataset", repo_id: "fixtures/cases", config: null, split: "train", revision: "main" },
    row_limit: 100,
    resolved_sha: "sha",
    source_code: "def process(row): pass",
    source_hash: "hash",
    segment_keys: [],
    tags: [],
    output_format: { kind: "text", schema: null, strict: true },
    processor_contract_version: "2",
    runtime_policy_version: "1",
    runtime_version: "1.3.0",
  },
};

test("job polling preserves focus and cancellation waits for confirmation", async ({ page }) => {
  await page.route("**/api/dataset-imports/ui-job", (route) => route.fulfill({ json: job }));
  await page.route("**/api/dataset-imports/ui-job/cancel", (route) =>
    route.fulfill({ json: { ...job, state: "cancelled", phase: "Cancelled" } }),
  );
  await page.goto("/dataset-imports/ui-job");
  const cancel = page.getByRole("button", { name: "Cancel import" });
  await cancel.focus();
  await page.waitForTimeout(1500);
  await expect(cancel).toBeFocused();
  await expect(page.getByText("Import specification")).toBeVisible();
  await expect(page.getByText("Processor source")).toBeHidden();
  await cancel.click();
  const dialog = page.getByRole("dialog", { name: "Cancel this import?" });
  await expect(dialog.getByRole("button", { name: "Keep import" })).toBeFocused();
  await dialog.getByRole("button", { name: "Keep import" }).click();
  await expect(cancel).toBeFocused();
  await cancel.click();
  await dialog.getByRole("button", { name: "Request cancellation" }).click();
  await expect(page.locator('.topbar .job-state[data-state="cancelled"]')).toBeVisible();
});

test("failed jobs show a safe diagnostic and offer retry", async ({ page }) => {
  const failed = {
    ...job,
    state: "failed",
    phase: "Failed",
    error: {
      category: "processor",
      message: "Invalid output",
      source_index: 4,
      line: 7,
      column: null,
      field_path: null,
    },
  };
  await page.route("**/api/dataset-imports/ui-job", (route) => route.fulfill({ json: failed }));
  await page.goto("/dataset-imports/ui-job");
  await expect(page.getByRole("alert")).toContainText("Invalid output");
  await expect(page.getByRole("alert")).toContainText("Source row 5 · line 7");
  await page.getByRole("link", { name: "Retry with this specification" }).click();
  await expect(page).toHaveURL(/\/dataset-imports\/new\?retry=ui-job/);
  await expect(page.getByLabel("Dataset name")).toHaveValue("Example import");
});

test("completed imports refresh the catalog before reporting dataset availability", async ({ page }) => {
  const response = await page.request.get("/api/datasets");
  const datasets: Array<{ id: string; name: string }> = await response.json();
  const dataset = datasets.find((item) => item.name === "deletion-target");
  if (!dataset) throw new Error("The import-result fixture is missing.");

  let catalogRequests = 0;
  let releaseCatalog: () => void = () => {};
  const catalogReady = new Promise<void>((resolve) => {
    releaseCatalog = resolve;
  });
  await page.route("**/api/datasets", async (route) => {
    catalogRequests += 1;
    if (catalogRequests === 1) {
      await route.fulfill({ json: [] });
    } else {
      await catalogReady;
      await route.continue();
    }
  });
  let jobRequests = 0;
  await page.route("**/api/dataset-imports/ui-job", (route) => {
    jobRequests += 1;
    return route.fulfill({
      json: jobRequests === 1 ? job : { ...job, state: "succeeded", phase: "completed", dataset_id: dataset.id },
    });
  });

  await page.goto("/dataset-imports/ui-job");
  await expect(page.locator('.topbar .job-state[data-state="succeeded"]')).toBeVisible();
  await expect(page.getByText("This dataset is in Trash or has been permanently deleted.")).toHaveCount(0);
  releaseCatalog();
  await expect(page.getByRole("button", { name: "Open dataset" })).toBeVisible();
  await expect(page.locator("aside").getByRole("link", { name: `Datasets ${datasets.length}` })).toBeVisible();
  await expect(page.getByRole("link", { name: "All import jobs" })).toHaveCount(0);
  await page.getByRole("button", { name: "Open dataset" }).click();
  await expect(page).toHaveURL(new RegExp(`/datasets/${dataset.id}$`));
});

test("completed imports still report a genuinely removed dataset", async ({ page }) => {
  await page.route("**/api/dataset-imports/ui-job", (route) =>
    route.fulfill({ json: { ...job, state: "succeeded", phase: "completed" } }),
  );
  await page.goto("/dataset-imports/ui-job");
  await expect(page.getByText("This dataset is in Trash or has been permanently deleted.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open dataset" })).toHaveCount(0);
});

test("review lets users choose and validate the imported dataset output format", async ({ page }) => {
  const expires_at = new Date(Date.now() + 3600_000).toISOString();
  await page.route("**/api/dataset-source-samples", (route) =>
    route.fulfill({
      json: {
        id: "sample",
        source: job.spec.source,
        resolved_sha: "sha",
        row_limit: 100,
        rows: [{ text: "A question", label: "An answer" }],
        columns: [
          { name: "text", types: ["string"] },
          { name: "label", types: ["string"] },
        ],
        expires_at,
      },
    }),
  );
  await page.route("**/api/dataset-previews", (route) =>
    route.fulfill({
      json: {
        id: "preview",
        sample_id: "sample",
        resolved_sha: "sha",
        source_hash: "hash",
        valid: true,
        rows_kept: 1,
        rows_dropped: 0,
        expires_at,
        rows: [
          {
            source_index: 0,
            status: "kept",
            error: null,
            example: {
              conversation: [{ role: "user", content: "A question" }],
              tools: [],
              expected_output: "An answer",
              extras: {},
              segments: {},
            },
          },
        ],
      },
    }),
  );
  const output = {
    kind: "json_schema",
    strict: true,
    schema: {
      type: "object",
      properties: { answer: { type: "string" } },
      required: ["answer"],
      additionalProperties: false,
    },
  };
  const importedJob = { ...job, spec: { ...job.spec, output_format: output } };
  await page.route("**/api/dataset-imports", async (route) => {
    expect(route.request().postDataJSON().output_format).toEqual(output);
    await route.fulfill({ json: importedJob });
  });
  await page.route("**/api/dataset-imports/ui-job", (route) => route.fulfill({ json: importedJob }));
  await page.goto("/dataset-imports/new");
  await page.getByLabel("Dataset name").fill("With output format");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Dataset repository").fill("fixtures/cases");
  await page.getByRole("button", { name: "Load sample" }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.locator(".cm-content")).toContainText('"extras"');
  await page.getByRole("button", { name: "Run preview" }).click();
  await page.getByRole("button", { name: "Continue to review" }).click();
  const editor = page.locator(".import-output-format");
  await editor.getByLabel("Output format").selectOption("json_schema");
  await expect(editor.getByText("About this output (optional)")).toBeVisible();
  await expect(editor.getByText("Upload JSON")).toHaveCount(0);
  await expect(editor.getByText("Download JSON")).toHaveCount(0);
  await editor.getByRole("button", { name: "Add field", exact: true }).click();
  await editor.getByLabel("Field name").fill("answer");
  await editor.getByLabel("Field name").press("Enter");
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.getByRole("button", { name: "Continue to review" }).click();
  await expect(editor.getByLabel("Field name")).toHaveValue("answer");
  await editor.getByLabel("Field name").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/import-output-review.png", fullPage: true });
  await editor.getByRole("button", { name: "JSON", exact: true }).click();
  await editor.getByRole("textbox", { name: "JSON Schema" }).fill("{");
  await expect(page.getByRole("button", { name: "Import dataset" })).toBeDisabled();
  await editor.getByRole("textbox", { name: "JSON Schema" }).fill(JSON.stringify(output.schema));
  await page.getByRole("button", { name: "Import dataset" }).click();
  await expect(page).toHaveURL(/\/dataset-imports\/ui-job$/);
});
