import assert from "node:assert/strict";
import { test } from "node:test";
import { getImport, listImports } from "../app/features/dataset-imports/transport";

test("historical and future job versions remain readable", async () => {
  const originalFetch = globalThis.fetch;
  const job = {
    id: "old",
    name: "old",
    state: "failed",
    phase: "failed",
    rows_loaded: 0,
    rows_kept: 0,
    rows_dropped: 0,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
    dataset_id: null,
    error: null,
    spec: {
      source: { kind: "hf_dataset", repo_id: "org/data", config: null, split: "train", revision: "main" },
      row_limit: 1,
      resolved_sha: "sha",
      source_code: "code",
      source_hash: "hash",
      segment_keys: [],
      tags: [],
      processor_contract_version: "1",
      runtime_policy_version: "99",
      runtime_version: "old",
    },
  };
  try {
    globalThis.fetch = async (input) =>
      new Response(JSON.stringify(String(input).endsWith("/old") ? job : { jobs: [job] }));
    assert.deepEqual((await listImports())[0].spec, job.spec);
    assert.deepEqual((await getImport("old")).spec, job.spec);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
