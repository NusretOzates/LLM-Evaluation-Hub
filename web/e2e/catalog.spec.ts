import { expect, test } from "@playwright/test";

test("browse a real catalog, retain special tags, reset page facets and mutate links", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) requests.push(request.url());
  });
  await page.goto("/datasets");
  await page.getByRole("link", { name: "Tags", exact: true }).click();
  await expect(page.getByRole("button", { name: "__proto__", exact: true })).toBeVisible();
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await expect(page.getByRole("heading", { name: "team/cases %?#", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/datasets\/[0-9a-f-]{36}$/);
  await expect(page.getByLabel("Segment", { exact: true })).toHaveValue("group");
  await page.getByLabel("Segment value").selectOption({ label: "a" });
  await page.getByRole("link", { name: "Next page" }).click();
  await expect(page.getByText("Synthetic row 51", { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("Segment value")).toHaveValue("all");
  await page.getByLabel("Segment value").selectOption({ label: "c" });
  await expect(page.getByText("No rows on this page match.")).toHaveCount(0);
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/row=52/);
  await expect(page.getByRole("heading", { name: "Example 52 of 61" })).toBeVisible();
  const requestsBeforeSelection = requests.length;
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/row=53/);
  await expect(page.getByRole("heading", { name: "Example 53 of 61" })).toBeVisible();
  expect(requests.length).toBe(requestsBeforeSelection);
  await page.keyboard.press("k");
  await expect(page).toHaveURL(/row=52/);
  await page.getByRole("button", { name: "Dataset details" }).click();
  await page.getByLabel("Tag to add").selectOption("__proto__");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("button", { name: "Remove __proto__" })).toBeVisible();
  await page.getByRole("button", { name: "Remove __proto__" }).click();
  await expect(page.getByRole("button", { name: "Remove __proto__" })).toHaveCount(0);
  await page.getByRole("button", { name: "JSON", exact: true }).click();
  await expect(page.locator("pre.raw")).toContainText('"conversation"');
  expect(errors).toEqual([]);
});

test("blocked preferences and clipboard leave browsing usable", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get: () => {
        throw new Error("Storage denied");
      },
    });
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: () => Promise.reject(new Error("Clipboard denied")) },
    });
  });
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await page.getByRole("button", { name: "Copy", exact: true }).click();
  await expect(page.getByRole("button", { name: "Copy failed" })).toBeVisible();
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/row=2/);
});

for (const width of [1440, 1100, 768]) {
  test(`inspector remains usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/datasets");
    await page.getByRole("link", { name: "team/cases %?#" }).click();
    await expect(page.getByRole("heading", { name: /^Example / })).toBeVisible();
    await page.getByRole("button", { name: "Next row", exact: true }).click();
    await expect(page).toHaveURL(/row=2/);
    await page.screenshot({ path: `test-results/inspector-${width}.png`, fullPage: true });
  });
}

test("direct links cross row-page boundaries, preserve history and show URL errors", async ({ page }) => {
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await expect(page).toHaveURL(/\/datasets\/[0-9a-f-]{36}$/);
  const detail = new URL(page.url()).pathname;
  await page.goto(`${detail}?row=50`);
  await expect(page.getByRole("heading", { name: "Example 50 of 61" })).toBeVisible();
  await page.keyboard.press("j");
  await expect(page.getByRole("heading", { name: "Example 51 of 61" })).toBeVisible();
  await expect(page).toHaveURL(/offset=50&row=51/);
  await page.keyboard.press("k");
  await expect(page.getByRole("heading", { name: "Example 50 of 61" })).toBeVisible();
  await page.getByRole("link", { name: "Datasets", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Datasets", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Example 50 of 61" })).toBeVisible();
  await page.goto(`${detail}?row=9007199254740992`);
  await expect(page.getByRole("alert")).toContainText("safe whole number");
  await page.goto(`${detail}?offset=9999`);
  await expect(page.getByText("This page is past the last row.", { exact: false })).toBeVisible();
  await page.goto("/datasets/not-a-dataset");
  await expect(page.getByRole("alert")).toContainText("unknown dataset");
});

test("narrow inspector sheets preserve desktop preferences and return focus to the selected example", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  const examples = page.getByRole("button", { name: "Row list" });
  await examples.click();
  const sheet = page.getByRole("dialog", { name: "Examples" });
  await expect(sheet).toBeVisible();
  await sheet.getByRole("link", { name: /^#2 / }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByRole("heading", { name: "Example 2 of 61" })).toBeFocused();
  await page.getByRole("button", { name: "Dataset details" }).click();
  await expect(page.getByRole("dialog", { name: "Dataset details" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Dataset details" })).toBeFocused();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.locator(".inspector")).toHaveAttribute("data-index", "true");
});

test("reader preserves supplied empty system messages and keeps long content within its pane", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.route("**/api/dataset-ids/*/examples?*", (route) =>
    route.fulfill({
      json: {
        total: 1,
        offset: 0,
        limit: 50,
        examples: [
          {
            conversation: [
              { role: "system", content: "" },
              {
                role: "user",
                content: [
                  { type: "text", text: "Long content ".repeat(100) },
                  { type: "image", url: null, path: "fixture.png" },
                ],
              },
              {
                role: "assistant",
                content: "Answer",
                thinking: "Reasoning",
                tool_calls: [
                  {
                    id: "call-1",
                    type: "function",
                    function: { name: "lookup", arguments: { value: "x".repeat(300) } },
                  },
                ],
              },
              { role: "tool", content: '{"result":true}', tool_call_id: "call-1", name: "lookup" },
            ],
            expected_output: "",
            extras: { technical: "x".repeat(500) },
            segments: {},
            tools: [],
          },
        ],
      },
    }),
  );
  await page.goto("/datasets");
  await page.getByRole("link", { name: "team/cases %?#" }).click();
  await expect(page.getByText("Empty message")).toBeVisible();
  await expect(page.getByText("[image]", { exact: false })).toBeVisible();
  await expect(page.getByText("lookup(", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Thinking", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Expected output" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.getByRole("button", { name: "Row list" }).click();
  const search = page.getByLabel("Filter rows or go to a row number");
  await search.fill("j");
  await page.keyboard.press("j");
  await expect(search).toHaveValue("jj");
  await expect(page).not.toHaveURL(/row=2/);
});
