import assert from "node:assert/strict";
import { test } from "node:test";
import { getImport, listImports } from "../app/features/dataset-imports/transport";

test("current import job is readable", async () => {
  const originalFetch = globalThis.fetch;
  const job = {
    id: "current",
    name: "current",
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
      output_format: { kind: "text", schema: null, strict: true },
      processor_contract_version: "2",
      runtime_policy_version: "1",
      runtime_version: "1.3.0",
    },
  };
  try {
    globalThis.fetch = async (input) =>
      new Response(JSON.stringify(String(input).endsWith("/current") ? job : { jobs: [job] }));
    assert.deepEqual((await listImports())[0].spec, job.spec);
    assert.deepEqual((await getImport("current")).spec, job.spec);
    job.spec.processor_contract_version = "1";
    await assert.rejects(getImport("current"), /unexpected job specification/);
    job.spec.processor_contract_version = "2";
    job.spec.runtime_policy_version = "99";
    await assert.rejects(getImport("current"), /unexpected job specification/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
