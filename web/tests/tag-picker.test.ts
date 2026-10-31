import assert from "node:assert/strict";
import test from "node:test";
import { toggleTagPath } from "../app/shared/tag-picker";

test("choosing a child replaces its ancestor and preserves siblings and other trees", () => {
  assert.deepEqual(toggleTagPath(["Benchmarks", "Language/English"], "Benchmarks/Reasoning"), [
    "Language/English",
    "Benchmarks/Reasoning",
  ]);
  assert.deepEqual(toggleTagPath(["Benchmarks/Reasoning"], "Benchmarks/Tool use"), [
    "Benchmarks/Reasoning",
    "Benchmarks/Tool use",
  ]);
});
test("choosing a broader tag replaces descendants but respects path boundaries", () => {
  assert.deepEqual(toggleTagPath(["Benchmarks/Reasoning", "Benchmarks/Tool use", "Benchmarks extra"], "Benchmarks"), [
    "Benchmarks extra",
    "Benchmarks",
  ]);
  assert.deepEqual(toggleTagPath(["Benchmarks"], "Benchmarks"), []);
});
