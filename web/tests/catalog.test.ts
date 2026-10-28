import assert from "node:assert/strict";
import { test } from "node:test";
import { flattenTags, tagForest } from "../app/catalog";
import { parseExamplePage, parseTagForest, parseMessage } from "../app/catalog-parsers";
import { readPosition, selectedRow, messageText } from "../app/features/dataset-inspector/model";
import { subtreeCounts } from "../app/shared/catalog-view";
import type { Dataset, ExamplePage } from "../app/catalog-types";

for (const name of ["__proto__", "constructor", "toString", "Türkçe"]) {
  test(`domain key ${name} survives creation, JSON and parsing`, () => {
    assert.deepEqual(Object.keys(JSON.parse(JSON.stringify(tagForest("", name)))), [name]);
    const forest = parseTagForest(
      JSON.parse(`{${JSON.stringify(name)}:{"path":${JSON.stringify(name)},"children":{}}}`),
    );
    assert.equal(flattenTags(forest)[0].path, name);
    assert.deepEqual(Object.keys(forest), [name]);
  });
}

test("positions preserve row/page boundaries and reject imprecise numbers", () => {
  assert.deepEqual(readPosition(new URLSearchParams("row=51")), { offset: 50, row: 51 });
  assert.deepEqual(readPosition(new URLSearchParams("offset=50&row=52")), { offset: 50, row: 52 });
  for (const value of ["-1", "Infinity", "1.2", "9007199254740992", "9".repeat(400)]) {
    assert.throws(() => readPosition(new URLSearchParams(`row=${value}`)));
  }
  const page: ExamplePage = {
    offset: 50,
    limit: 50,
    total: 51,
    examples: [{ conversation: [{ role: "user", content: "row" }], expected_output: null, extras: {}, segments: {} }],
  };
  assert.equal(selectedRow(page, "51"), 51);
  assert.equal(selectedRow(page, "1"), 51);
});

test("every backend message variant preserves its transport payload", () => {
  const messages = [
    { role: "system", content: "" },
    {
      role: "user",
      content: [
        { type: "text", text: "Hello" },
        { type: "image", url: "https://example.test/image.png", path: null },
      ],
    },
    {
      role: "assistant",
      content: null,
      thinking: "Plan",
      tool_calls: [{ id: "call-1", type: "function", function: { name: "lookup", arguments: { city: "Ankara" } } }],
    },
    { role: "tool", content: "{}", tool_call_id: "call-1", name: "lookup" },
  ];
  const parsed = messages.map(parseMessage);
  assert.deepEqual(parsed, messages);
  assert.equal(messageText(parsed[1].content), "Hello\n[image]");
});

test("malformed required shapes fail rather than becoming empty data", () => {
  const row = { conversation: [{ role: "user", content: "test" }], expected_output: null, extras: {}, segments: {} };
  const page = { offset: 0, limit: 20, total: 1, examples: [row] };
  assert.equal(parseExamplePage(page).examples.length, 1);
  for (const bad of [
    { ...row, extras: [] },
    { ...row, segments: { language: 10 } },
    { ...row, conversation: [] },
    { ...row, expected_output: undefined },
  ]) {
    assert.throws(() => parseExamplePage({ ...page, examples: [bad] }));
  }
  for (const message of [
    { role: "unknown", content: "x" },
    { role: "tool", content: "x", tool_call_id: "" },
    { role: "assistant", content: null, thinking: null, tool_calls: [] },
    { role: "user", content: [{ type: "image", url: "a", path: "b" }] },
  ])
    assert.throws(() => parseMessage(message));
});

test("subtree counts count each dataset once despite multiple descendants", () => {
  const dataset: Dataset = {
    id: "id",
    name: "name",
    created_at: "2026-10-26T00:00:00Z",
    processor_id: "test",
    source_type: "test",
    repo_id: null,
    config: null,
    split: null,
    revision: null,
    resolved_sha: null,
    row_limit: null,
    rows_loaded: 1,
    rows_kept: 1,
    rows_dropped: 0,
    segment_keys: [],
    tags: ["A/B", "A/C", "A"],
  };
  assert.deepEqual(
    [...subtreeCounts([dataset])],
    [
      ["A", 1],
      ["A/B", 1],
      ["A/C", 1],
    ],
  );
});

test("HTTP failures preserve useful status and validation messages", async (context) => {
  const { listDatasets, CatalogError } = await import("../app/catalog");
  const fetchMock = context.mock.method(globalThis, "fetch");
  fetchMock.mock.mockImplementation(
    async () => new Response(JSON.stringify({ detail: [{ msg: "Invalid tag" }] }), { status: 422 }),
  );
  await assert.rejects(
    listDatasets(null),
    (error: unknown) => error instanceof CatalogError && error.status === 422 && error.message === "Invalid tag",
  );
  fetchMock.mock.mockImplementation(async () => new Response("Bad gateway", { status: 502 }));
  await assert.rejects(listDatasets(null), (error: unknown) => error instanceof CatalogError && error.status === 502);
  fetchMock.mock.mockImplementation(async () => new Response("not JSON", { status: 200 }));
  await assert.rejects(listDatasets(null), CatalogError);
  fetchMock.mock.mockImplementation(async () => {
    throw new TypeError("offline");
  });
  await assert.rejects(listDatasets(null), (error: unknown) => error instanceof CatalogError && error.status === 0);
  const controller = new AbortController();
  controller.abort();
  const aborted = new DOMException("Aborted", "AbortError");
  fetchMock.mock.mockImplementation(async () => {
    throw aborted;
  });
  await assert.rejects(listDatasets(null, controller.signal), (error: unknown) => error === aborted);
});
