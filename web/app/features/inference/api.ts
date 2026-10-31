import { detailMessage } from "../../catalog-parsers";
import { CatalogError } from "../../catalog";
import type { JsonValue } from "../../catalog-types";

import type * as Schema from "../../api-schema";
export type Output = Required<Schema.OutputFormat_Output>;
export type Profile = Required<Schema.ConnectionProfile>;
export type Generation = Required<Schema.Generation>;
export type RunSpec = Omit<Required<Schema.RunSpec>, "generation" | "output_overrides"> & {
  generation: Generation;
  output_overrides: Record<string, Output>;
};
export type RunDataset = Omit<Schema.FrozenDataset, "output"> & { output: Output };
export type Run = Omit<Schema.RunView, "datasets"> & { datasets: RunDataset[] };
export type Result = Required<Schema.RowResult>;
export const defaultOutput: Output = { kind: "text", schema: null, strict: true };
export const defaultGeneration: Generation = {
  max_tokens: null,
  temperature: null,
  top_p: null,
  seed: null,
  effort: null,
  thinking: null,
  advanced: {},
};
export const newProfile: Profile = {
  id: "",
  name: "",
  base_url: "",
  model: "",
  api_key_env: null,
  reasoning_mode: "effort",
  effort_levels: ["low", "medium", "high"],
  effort_path: "reasoning_effort",
  thinking_path: "thinking.enabled",
  max_tokens_field: "max_completion_tokens",
};
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === "string");
const nullableString = (v: unknown) => v === null || typeof v === "string";
const json = (v: unknown): v is JsonValue =>
  v === null ||
  typeof v === "string" ||
  typeof v === "boolean" ||
  (typeof v === "number" && Number.isFinite(v)) ||
  (Array.isArray(v) && v.every(json)) ||
  (object(v) && Object.values(v).every(json));
function parseProfile(v: unknown): Profile {
  if (
    !object(v) ||
    !["id", "name", "base_url", "model", "effort_path", "thinking_path"].every((k) => typeof v[k] === "string") ||
    !nullableString(v.api_key_env) ||
    !strings(v.effort_levels) ||
    !["effort", "thinking"].includes(String(v.reasoning_mode)) ||
    !["max_tokens", "max_completion_tokens"].includes(String(v.max_tokens_field))
  )
    throw new Error("Invalid connection response.");
  return v as Profile;
}
function parseOutput(v: unknown): Output {
  if (
    !object(v) ||
    !["text", "json_object", "json_schema"].includes(String(v.kind)) ||
    typeof v.strict !== "boolean" ||
    !(v.schema === null || (object(v.schema) && json(v.schema)))
  )
    throw new Error("Invalid output format response.");
  return v as Output;
}
function parseRun(v: unknown): Run {
  if (
    !object(v) ||
    !["id", "state", "created_at", "updated_at"].every((k) => typeof v[k] === "string") ||
    typeof v.completed !== "number" ||
    typeof v.total !== "number" ||
    !object(v.spec) ||
    !json(v.spec) ||
    !Array.isArray(v.datasets) ||
    !v.datasets.every(
      (d) =>
        object(d) &&
        typeof d.id === "string" &&
        typeof d.name === "string" &&
        typeof d.snapshot_format_version === "number" &&
        typeof d.rows === "number" &&
        typeof d.completed === "number" &&
        typeof d.errors === "number" &&
        typeof d.input_available === "boolean" &&
        (() => {
          try {
            parseOutput(d.output);
            return true;
          } catch {
            return false;
          }
        })(),
    )
  )
    throw new Error("Invalid run response.");
  return v as Run;
}
function parseResult(v: unknown): Result {
  if (
    !object(v) ||
    typeof v.dataset_id !== "string" ||
    typeof v.ordinal !== "number" ||
    typeof v.source_index !== "number" ||
    typeof v.status !== "string" ||
    !strings(v.validation_errors) ||
    ![v.content, v.finish_reason, v.error].every(nullableString) ||
    ![v.raw_response, v.tool_calls, v.parsed, v.usage].every(json) ||
    !(v.latency_ms === null || typeof v.latency_ms === "number") ||
    typeof v.attempts !== "number"
  )
    throw new Error("Invalid result response.");
  return v as Result;
}
function array<T>(v: unknown, parse: (x: unknown) => T): T[] {
  if (!Array.isArray(v)) throw new Error("Invalid list response.");
  return v.map(parse);
}
export async function request<T>(
  path: string,
  parse: (value: unknown) => T,
  body?: unknown,
  method = body === undefined ? "GET" : "POST",
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const value: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new CatalogError(detailMessage(value), response.status);
  return parse(value);
}
export const api = {
  input: (runId: string, datasetId: string, ordinal: number) =>
    request(
      `/inference/runs/${encodeURIComponent(runId)}/datasets/${encodeURIComponent(datasetId)}/inputs/${ordinal}`,
      (v) => {
        if (!object(v) || !json(v)) throw new Error("Invalid input response.");
        return v;
      },
    ),
  profiles: () => request("/connections", (v) => array(v, parseProfile)),
  saveProfile: (p: Profile) => request("/connections", parseProfile, p),
  deleteProfile: (id: string) =>
    request(`/connections/${encodeURIComponent(id)}`, () => undefined, undefined, "DELETE"),
  output: (id: string) => request(`/dataset-ids/${encodeURIComponent(id)}/output-format`, parseOutput),
  saveOutput: (id: string, output: Output) =>
    request(`/dataset-ids/${encodeURIComponent(id)}/output-format`, parseOutput, output, "PUT"),
  runs: () => request("/inference/runs", (v) => array(v, parseRun)),
  run: (id: string) => request(`/inference/runs/${encodeURIComponent(id)}`, parseRun),
  create: (spec: RunSpec) => request("/inference/runs", parseRun, spec),
  results: (id: string, offset: number, filter: string) => {
    const query = new URLSearchParams({ offset: String(offset), limit: "20" });
    if (filter === "errors") query.set("errors_only", "true");
    else if (filter !== "all") query.set("dataset_id", filter);
    return request(`/inference/runs/${encodeURIComponent(id)}/results?${query}`, (v) => {
      if (!object(v) || typeof v.total !== "number" || typeof v.offset !== "number" || typeof v.limit !== "number")
        throw new Error("Invalid result page.");
      return { results: array(v.results, parseResult), total: v.total, offset: v.offset, limit: v.limit };
    });
  },
  action: (id: string, action: "cancel" | "resume") =>
    request(`/inference/runs/${encodeURIComponent(id)}/${action}`, () => undefined, {}, "POST"),
  preview: (body: unknown) =>
    request(
      "/inference/preview",
      (v) => {
        if (!object(v) || !json(v)) throw new Error("Invalid preview response.");
        return v;
      },
      body,
    ),
  test: (body: unknown) =>
    request(
      "/inference/test",
      (v) => {
        if (!object(v) || !json(v)) throw new Error("Invalid test response.");
        return v;
      },
      body,
    ),
};
