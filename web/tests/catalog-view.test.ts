import assert from "node:assert/strict";
import test from "node:test";
import type { Dataset } from "../app/catalog-types";
import { filterDatasets, parseCatalogFilters } from "../app/shared/catalog-view";

const dataset = (name: string, tags: string[]) => ({ name, tags }) as Dataset;
const datasets = [
  dataset("Alpha", ["Benchmarks/Reasoning", "Language/English"]),
  dataset("Beta", ["Benchmarks/Tool use", "Language/English"]),
  dataset("Gamma", ["Benchmarks"]),
  dataset("Boundary", ["BenchmarksX"]),
];
const available = new Set(["Benchmarks", "Benchmarks/Reasoning", "Benchmarks/Tool use", "Language/English"]);
test("name and tag filters combine, matching direct and descendant assignments", () => {
  assert.deepEqual(
    filterDatasets(datasets, { query: "", tags: ["Benchmarks"] }, available).map((item) => item.name),
    ["Alpha", "Beta", "Gamma"],
  );
  assert.deepEqual(
    filterDatasets(datasets, { query: " ALP ", tags: ["Benchmarks/Reasoning", "Language/English"] }, available).map(
      (item) => item.name,
    ),
    ["Alpha"],
  );
  assert.deepEqual(
    filterDatasets(datasets, { query: "Beta", tags: ["Benchmarks/Reasoning", "Language/English"] }, available),
    [],
  );
  assert.deepEqual(filterDatasets(datasets, { query: "", tags: ["Deleted"] }, available), []);
});

test("URL filters ignore empty values and deduplicate without changing order", () => {
  const params = new URLSearchParams("q=ALP&tag=Benchmarks&tag=&tag=Benchmarks&tag=Language%2FEnglish");
  assert.deepEqual(parseCatalogFilters(params), { query: "ALP", tags: ["Benchmarks", "Language/English"] });
});
