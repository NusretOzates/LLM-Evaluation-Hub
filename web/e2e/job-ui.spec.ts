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
    processor_contract_version: "1",
    runtime_policy_version: "1",
    runtime_version: "1",
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
