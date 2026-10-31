import { expect, type Page, test } from "@playwright/test";

const processorCode = `def process(row: dict) -> dict | None:
    return {
        "conversation": [{"role": "user", "content": row["text"]}],
        "tools": row["tools"],
        "expected_output": row["label"],
        "segments": {
            "language": str(row["language"]),
            "difficulty_bucket": str(row["difficulty"]),
        },
    }
`;

async function openProcessor(page: Page, name: string, repo = "fixtures/cases") {
  await page.goto("/dataset-imports/new");
  await page.getByLabel("Dataset name").fill(name);
  await page.getByRole("checkbox", { name: "Browser", exact: true }).check();
  await page.getByRole("checkbox", { name: "__proto__", exact: true }).check();
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  await page.getByLabel("Dataset repository").fill(repo);
  await page.getByRole("button", { name: "Load sample" }).click();
  await expect(page.getByText(/3 sample rows/)).toBeVisible();
  await expect(page.getByText(/resolved to synthetic-/)).toBeVisible();
  await page.getByRole("checkbox", { name: "language", exact: true }).check();
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Processor and preview" })).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText('"language": str(row["language"])');
}

async function editProcessor(page: Page, code = processorCode) {
  const editor = page.locator(".cm-content[contenteditable='true']");
  await expect(editor).toBeVisible();
  await editor.fill(code);
  return editor;
}

async function previewRows(page: Page) {
  await page.getByRole("button", { name: "Run preview" }).click();
  await expect(page.getByRole("heading", { name: "Preview rows" })).toBeVisible();
}

async function submitFromReview(page: Page) {
  await page.getByRole("button", { name: "Continue to review" }).click();
  await expect(page.getByRole("heading", { name: "Review import" })).toBeVisible();
  await expect(page.getByText(/Browser, __proto__/)).toBeVisible();
  await page.getByRole("button", { name: "Import dataset" }).click();
}

test("imports three row-specific tool schemas through Monty and inspects the published snapshot", async ({
  page,
  context,
}) => {
  const externalRequests: string[] = [];
  page.on("request", (request) => {
    if (!new URL(request.url()).hostname.match(/^(127\.0\.0\.1|localhost)$/)) {
      externalRequests.push(request.url());
    }
  });
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await openProcessor(page, "qa-row-tools-e2e");
  await editProcessor(page);
  await previewRows(page);

  const tools = page.locator(".preview-example .available-tools");
  await expect(tools).toContainText("lookup_order");
  await expect(tools).toContainText("Look up an order by identifier.");
  await page.getByRole("button", { name: /Source row 2/ }).click();
  await expect(tools).toContainText("search_catalog");
  await expect(tools).toContainText("Search the product catalog.");
  await page.getByRole("button", { name: /Source row 3/ }).click();
  await expect(tools).toContainText("No tools");

  await page.getByRole("button", { name: /Source row 1/ }).click();
  await expect(tools).toContainText("lookup_order");
  await page.screenshot({ path: "test-results/dataset-import-preview-tools.png", fullPage: true });
  await submitFromReview(page);
  await expect(page).toHaveURL(/\/datasets\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name: "Row 1 of 3" })).toBeVisible();
  const inspectorTools = page.locator(".inspector-tools");
  await expect(inspectorTools).toContainText("lookup_order");
  await page.getByRole("button", { name: "Next row" }).click();
  await expect(page.getByRole("heading", { name: "Row 2 of 3" })).toBeVisible();
  await expect(inspectorTools).toContainText("search_catalog");
  await page.screenshot({ path: "test-results/dataset-import-inspector-tools.png", fullPage: true });
  await inspectorTools.getByRole("button", { name: "Tools JSON", exact: true }).click();
  await expect(inspectorTools.locator("pre.raw")).toContainText('"required": [');
  await expect(inspectorTools.locator("pre.raw")).toContainText('"query":');
  await inspectorTools.getByRole("button", { name: "Copy tools", exact: true }).click();
  await expect(inspectorTools.getByRole("button", { name: "Tools copied" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("search_catalog");

  await page.getByRole("button", { name: "Next row" }).click();
  await expect(page.getByRole("heading", { name: "Row 3 of 3" })).toBeVisible();
  await expect(inspectorTools).toContainText("No tools");
  expect(externalRequests).toEqual([]);
});

test("surfaces processor errors, accepts correction, and invalidates a stale preview after keyboard edits", async ({
  page,
}) => {
  await openProcessor(page, "qa-preview-correction-e2e");
  const editor = await editProcessor(page, "def process(row: dict) -> dict | None:\n    return {\n");
  await previewRows(page);
  await expect(page.getByRole("alert")).toContainText("Preview failed validation.");

  await editor.fill(processorCode);
  await previewRows(page);
  await expect(page.locator(".preview-example .available-tools")).toContainText("lookup_order");
  const continueButton = page.getByRole("button", { name: "Continue to review" });
  await expect(continueButton).toBeEnabled();

  await editor.press("Control+End");
  await page.keyboard.press("Enter");
  await page.keyboard.type("# keyboard edit");
  await expect(page.locator(".preview-results")).toHaveCount(0);
  await expect(continueButton).toBeDisabled();
  await editor.press("Control+Z");
  await expect(editor).not.toContainText("# keyboard edit");
  await expect(continueButton).toBeDisabled();

  await previewRows(page);
  await expect(continueButton).toBeEnabled();
});

test("a malformed definition in a later source row fails the whole import without publishing", async ({ page }) => {
  const name = "qa-later-row-error-e2e";
  await openProcessor(page, name, "fixtures/later-error");
  await editProcessor(page);
  await previewRows(page);
  await expect(page.locator(".preview-results")).toContainText("3 kept");
  await submitFromReview(page);

  await expect(page.locator('.topbar .job-state[data-state="failed"]')).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByRole("alert")).toContainText("Source row 4");
  await page.goto("/datasets");
  await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0);
});

test("cancellation survives refresh, is rediscoverable, and retry requires a fresh sample", async ({ page }) => {
  const name = "qa-cancel-retry-e2e";
  await openProcessor(page, name, "fixtures/slow");
  await editProcessor(page);
  await previewRows(page);
  await submitFromReview(page);

  const state = page.locator(".topbar .job-state");
  await expect(state).toHaveAttribute("data-state", "running", { timeout: 10_000 });
  const jobUrl = page.url();
  await page.reload();
  await expect(page.locator(".topbar .job-state")).toHaveAttribute("data-state", "running", {
    timeout: 10_000,
  });
  await page.getByRole("button", { name: "Cancel import" }).click();
  await page
    .getByRole("dialog", { name: "Cancel this import?" })
    .getByRole("button", { name: "Request cancellation" })
    .click();
  await expect(page.locator('.topbar .job-state[data-state="cancelled"]')).toBeVisible({
    timeout: 10_000,
  });

  await page.getByRole("link", { name: "All import jobs" }).click();
  await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  await page.getByRole("link", { name, exact: true }).click();
  await expect(page.locator('.topbar .job-state[data-state="cancelled"]')).toBeVisible();
  await page.getByRole("link", { name: "Retry with this specification" }).click();
  await expect(page.getByLabel("Dataset name")).toHaveValue(name);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByLabel("Dataset repository")).toHaveValue("fixtures/slow");
  await expect(page.getByRole("button", { name: "Load sample" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeDisabled();
  expect(page.url()).not.toBe(jobUrl);
});

test("source edits during sampling re-enable Load sample and discard stale results", async ({ page }) => {
  await page.goto("/dataset-imports/new");
  await page.getByLabel("Dataset name").fill("qa-source-race-e2e");
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  const repository = page.getByLabel("Dataset repository");
  const rowLimit = page.getByLabel("Source-row limit");
  const load = page.getByRole("button", { name: "Load sample" });
  await repository.fill("fixtures/sample-delay");
  await load.click();
  await expect(load).toBeDisabled();

  await repository.fill("fixtures/cases");
  await expect(load).toBeEnabled();
  await load.click();
  await expect(page.getByText(/3 sample rows/)).toBeVisible();
  await expect(page.getByText(/resolved to synthetic-cases-sha/)).toBeVisible();

  await repository.fill("fixtures/sample-delay");
  await load.click();
  await expect(load).toBeDisabled();
  await rowLimit.fill("2");
  await expect(load).toBeEnabled();
  await load.click();
  await expect(page.getByText(/2 sample rows/)).toBeVisible();
  await expect(page.getByText(/resolved to synthetic-sample-delay-sha/)).toBeVisible();
  await expect(rowLimit).toHaveValue("2");
});

test("pending name checks cannot skip the source step or advance after a name edit", async ({ page }) => {
  await page.goto("/dataset-imports/new");
  const name = page.getByLabel("Dataset name");
  const next = page.getByRole("button", { name: "Continue", exact: true });
  await expect(name).toBeVisible();

  let releaseLookup = () => {};
  let lookupStarted = () => {};
  let lookupFinished = () => {};
  const started = new Promise<void>((resolve) => {
    lookupStarted = resolve;
  });
  const released = new Promise<void>((resolve) => {
    releaseLookup = resolve;
  });
  const finished = new Promise<void>((resolve) => {
    lookupFinished = resolve;
  });
  await page.route(
    "**/api/datasets",
    async (route) => {
      lookupStarted();
      await released;
      try {
        await route.continue();
      } finally {
        lookupFinished();
      }
    },
    { times: 1 },
  );

  await name.fill("qa-name-double-click-e2e");
  const firstRequest = page.waitForRequest("**/api/datasets");
  await next.dblclick();
  await started;
  releaseLookup();
  await finished;
  await (await firstRequest).response();
  await expect(page.getByLabel("Dataset repository")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load sample" })).toBeVisible();
  await expect(next).toBeDisabled();

  await page.goto("/dataset-imports/new");
  await expect(name).toBeVisible();
  const staleStarted = new Promise<void>((resolve) => {
    lookupStarted = resolve;
  });
  const staleReleased = new Promise<void>((resolve) => {
    releaseLookup = resolve;
  });
  const staleFinished = new Promise<void>((resolve) => {
    lookupFinished = resolve;
  });
  await page.route(
    "**/api/datasets",
    async (route) => {
      lookupStarted();
      await staleReleased;
      try {
        await route.continue();
      } finally {
        lookupFinished();
      }
    },
    { times: 1 },
  );
  await name.fill("team/cases %?#");
  const staleRequest = page.waitForRequest("**/api/datasets");
  await next.click();
  await staleStarted;
  await name.fill("qa-name-edited-e2e");
  releaseLookup();
  await staleFinished;
  await (await staleRequest).response();
  await expect(name).toHaveValue("qa-name-edited-e2e");
  await expect(page.getByRole("heading", { name: "Dataset details" })).toBeVisible();
  await expect(page.getByText(/already exists/i)).toHaveCount(0);
  await next.click();
  await expect(page.getByLabel("Dataset repository")).toBeVisible();
  await expect(next).toBeDisabled();
});

for (const width of [1440, 1100, 768]) {
  test(`dataset import form fits the viewport at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/dataset-imports/new");
    await expect(page.getByRole("heading", { name: "Dataset details" })).toBeVisible();
    await page.screenshot({ path: `test-results/import-form-${width}.png`, fullPage: true });
    const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(pageWidth).toBeLessThanOrEqual(width);
  });
}
