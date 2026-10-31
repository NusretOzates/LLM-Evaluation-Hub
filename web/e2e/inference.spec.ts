import { createServer, type Server } from "node:http";
import { expect, test } from "@playwright/test";
let server: Server;
test.beforeAll(async () => {
  server = createServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(
      JSON.stringify({
        id: "local",
        object: "chat.completion",
        created: 1,
        model: "fake",
        choices: [{ index: 0, finish_reason: "stop", message: { role: "assistant", content: "hello" } }],
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
      }),
    );
  });
  await new Promise<void>((resolve) => server.listen(18991, "127.0.0.1", resolve));
});
test.afterAll(async () => {
  await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
});
test("configure output and run a local example", async ({ page }) => {
  await page.goto("/connections");
  await page.getByRole("button", { name: "New connection" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Local fake");
  await page.getByLabel("Base URL").fill("http://127.0.0.1:18991/v1");
  await page.getByLabel("Model", { exact: true }).fill("fake");
  await expect(page.getByLabel("Reasoning controls").locator("option")).toHaveText([
    "Effort levels",
    "Thinking on/off",
  ]);
  await page.getByLabel("Reasoning controls").selectOption("thinking");
  await expect(page.getByLabel("Thinking request path")).toBeVisible();
  await expect(page.getByLabel("Effort values (comma-separated)")).toHaveCount(0);
  await page.getByLabel("Reasoning controls").selectOption("effort");
  await expect(page.getByLabel("Thinking request path")).toHaveCount(0);
  await page.getByLabel("Effort values (comma-separated)").fill("low, high");
  await page.getByRole("button", { name: "Save connection" }).click();
  await expect(page.getByRole("heading", { name: "Local fake" })).toBeVisible();
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await page.getByRole("link", { name: "Output settings" }).click();
  await page.getByLabel("Output format").selectOption("json_schema");
  await page.getByRole("button", { name: "Add field" }).click();
  const name = page.getByLabel("Field name");
  await name.fill("answer");
  await name.press("Enter");
  await expect(page.getByLabel("Field name")).toHaveValue("answer");
  await page.getByText("Field settings", { exact: true }).first().click();
  const values = page.getByLabel("Allowed values (JSON array)");
  await values.fill('["yes", "no"]');
  await values.blur();
  await page.getByRole("button", { name: "JSON", exact: true }).click();
  const json = page.getByRole("textbox", { name: "JSON Schema" });
  await expect(json).toHaveValue(/answer/);
  await json.fill("{");
  await expect(page.getByRole("button", { name: "Save defaults" })).toBeDisabled();
  await json.fill('{"type":"object","properties":{},"required":[],"additionalProperties":false}');
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(page.getByRole("status")).toContainText("saved");
  await page.reload();
  await page.getByRole("button", { name: "JSON", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "JSON Schema" })).toHaveValue(/additionalProperties/);
  await page.goto("/inference/new");
  await page.getByLabel("team/cases %?#").check();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Connection and generation" })).toBeVisible({ timeout: 5000 });
  await page.getByRole("combobox", { name: /Connection/ }).selectOption({ label: "Local fake · fake" });
  await expect(page.getByRole("combobox", { name: "Effort", exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Thinking", exact: true })).toHaveCount(0);
  await page.getByLabel("Requests per minute").fill("6000");
  await page.getByRole("button", { name: "Review" }).click();
  await page.getByRole("button", { name: "Preview request" }).click();
  await expect(page.getByRole("heading", { name: "Effective request" })).toBeVisible();
  await page.getByRole("button", { name: "Test example" }).click();
  await expect(page.getByRole("heading", { name: "Test response" })).toBeVisible();
  await page.getByRole("button", { name: "Create run" }).click();
  await expect(page.getByRole("heading", { name: "Run detail" })).toBeVisible();
  await expect(page.getByText("61 / 61 rows completed")).toBeVisible({ timeout: 15000 });
  await page.getByLabel("Filter results").selectOption("errors");
  await expect(page.getByText("Rows 1–20 of 61")).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("Rows 21–40 of 61")).toBeVisible();
});
test("independent schema drafts block saving until each is valid", async ({ page }) => {
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await page.getByRole("link", { name: "Output settings" }).click();
  await page.getByLabel("Output format").selectOption("json_schema");
  await page.getByRole("button", { name: "Add field" }).click();
  await page.getByRole("button", { name: "Add field" }).click();
  const names = page.getByLabel("Field name");
  await page.getByText("Field settings", { exact: true }).nth(0).click();
  await page.getByText("Field settings", { exact: true }).nth(1).click();
  const enums = page.getByLabel("Allowed values (JSON array)");
  await enums.nth(0).fill("[");
  await enums.nth(1).fill('["valid"]');
  await enums.nth(1).blur();
  await expect(page.getByRole("button", { name: "Save defaults" })).toBeDisabled();
  await enums.nth(0).fill('["fixed"]');
  await enums.nth(0).blur();
  await names.nth(1).fill("field");
  await names.nth(1).blur();
  await expect(page.getByRole("button", { name: "Save defaults" })).toBeDisabled();
  await names.nth(1).fill("second");
  await names.nth(1).blur();
  await expect(page.getByRole("button", { name: "Save defaults" })).toBeEnabled();
});
test("nested visual schema is editable at desktop and narrow widths", async ({ page }) => {
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await page.getByRole("link", { name: "Output settings" }).click();
  await page.getByLabel("Output format").selectOption("json_schema");
  await page.getByRole("button", { name: "Add field" }).click();
  const parent = page.locator(".schema-property").first();
  await parent.getByLabel("Field name").first().fill("record");
  await parent.getByLabel("Field name").first().press("Enter");
  const renamed = page.locator(".schema-property").first();
  await renamed.getByRole("combobox", { name: /Type/ }).first().selectOption("object");
  await renamed.getByRole("button", { name: "Add field" }).click();
  const child = page.locator(".schema-property .schema-property").first();
  await child.getByRole("combobox", { name: /^Type/ }).first().selectOption("array");
  await child.getByLabel("Allow null").last().check();
  await expect(child.getByLabel("Required").first()).toBeChecked();
  await page.screenshot({ path: "test-results/inference-schema-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 375, height: 850 });
  await page.screenshot({ path: "test-results/inference-schema-narrow.png", fullPage: true });
  await page.getByRole("button", { name: "JSON", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "JSON Schema" })).toHaveValue(/"array"/);
});
for (const theme of ["light", "dark"])
  test(`inference layout ${theme} narrow`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 850 });
    await page.addInitScript((value) => localStorage.setItem("evaluation-hub.theme", value), theme);
    await page.goto("/inference");
    await expect(page.getByRole("heading", { name: "Inference runs" })).toBeVisible();
    await page.screenshot({ path: `test-results/inference-${theme}-narrow.png`, fullPage: true });
  });
