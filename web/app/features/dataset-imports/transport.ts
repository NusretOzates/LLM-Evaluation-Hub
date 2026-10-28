import { CatalogError } from "../../shared/catalog-error";
import { parseExample as parseCatalogExample } from "../../catalog-parsers";
import type {
  DatasetPreview,
  Diagnostic,
  ImportJob,
  ImportJobState,
  ImportLimits,
  ImportSources,
  ImportedExample,
  JsonValue,
  SourceCoordinates,
  SourceSample,
} from "./contracts";

const API = "/api";
export async function getImportSources(signal?: AbortSignal): Promise<ImportSources> {
  return request("/dataset-sources", { method: "GET", signal }, (value) => {
    if (!isRecord(value) || !Array.isArray(value.sources) || !isRecord(value.limits))
      return invalid("available sources");
    const sources = value.sources.map((source) => {
      if (!isRecord(source) || source.kind !== "hf_dataset") return invalid("source choice");
      return { kind: "hf_dataset" as const, label: string(source.label) };
    });
    if (!sources.some((source) => source.kind === "hf_dataset")) return invalid("Hugging Face source choice");
    const limits: ImportLimits = {
      max_rows: number(value.limits.max_rows),
      sample_rows: number(value.limits.sample_rows),
      max_source_bytes: number(value.limits.max_source_bytes),
    };
    if (limits.max_rows < 1 || limits.sample_rows < 1 || limits.max_source_bytes < 1) return invalid("source limits");
    return { sources, limits };
  });
}
export async function loadSourceSample(
  source: SourceCoordinates,
  row_limit: number,
  signal?: AbortSignal,
): Promise<SourceSample> {
  return request(
    "/dataset-source-samples",
    { method: "POST", body: JSON.stringify({ source, row_limit }), signal },
    parseSample,
  );
}
export async function runDatasetPreview(
  sample_id: string,
  source_code: string,
  segment_keys: string[],
  signal?: AbortSignal,
): Promise<DatasetPreview> {
  return request(
    "/dataset-previews",
    { method: "POST", body: JSON.stringify({ sample_id, source_code, segment_keys }), signal },
    parsePreview,
  );
}
export async function submitImport(
  preview_id: string,
  name: string,
  tags: string[],
  idempotency_key: string,
): Promise<ImportJob> {
  return request(
    "/dataset-imports",
    { method: "POST", body: JSON.stringify({ preview_id, name, tags, idempotency_key }) },
    parseJob,
  );
}
export async function listImports(signal?: AbortSignal): Promise<ImportJob[]> {
  return request("/dataset-imports", { method: "GET", signal }, (value) => {
    if (!isRecord(value) || !Array.isArray(value.jobs)) return invalid("job list");
    return value.jobs.map(parseJob);
  });
}
export async function getImport(id: string, signal?: AbortSignal): Promise<ImportJob> {
  return request(`/dataset-imports/${encodeURIComponent(id)}`, { method: "GET", signal }, parseJob);
}
export async function cancelImport(id: string): Promise<ImportJob> {
  return request(`/dataset-imports/${encodeURIComponent(id)}/cancel`, { method: "POST" }, parseJob);
}
async function request<T>(path: string, init: RequestInit, parse: (value: unknown) => T): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new CatalogError("The dataset import API is not reachable.", 0);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new CatalogError(errorMessage(body), response.status);
  return parse(body);
}
function parseSample(value: unknown): SourceSample {
  if (!isRecord(value) || !Array.isArray(value.rows) || !Array.isArray(value.columns)) return invalid("source sample");
  return {
    id: string(value.id),
    source: parseSource(value.source),
    resolved_sha: string(value.resolved_sha),
    row_limit: number(value.row_limit),
    rows: value.rows.map(jsonObject),
    columns: value.columns.map((column) => {
      if (!isRecord(column) || !Array.isArray(column.types)) return invalid("source columns");
      return { name: string(column.name), types: column.types.map(string) };
    }),
    expires_at: string(value.expires_at),
  };
}
function parsePreview(value: unknown): DatasetPreview {
  if (!isRecord(value) || !Array.isArray(value.rows)) return invalid("preview");
  return {
    id: nullableString(value.id),
    sample_id: string(value.sample_id),
    resolved_sha: string(value.resolved_sha),
    source_hash: string(value.source_hash),
    rows: value.rows.map((row) => {
      if (!isRecord(row) || (row.status !== "kept" && row.status !== "skipped" && row.status !== "failed"))
        return invalid("preview row");
      return {
        source_index: number(row.source_index),
        status: row.status,
        example: row.example === null ? null : parseExample(row.example),
        error: row.error === null ? null : parseDiagnostic(row.error),
      };
    }),
    rows_kept: number(value.rows_kept),
    rows_dropped: number(value.rows_dropped),
    valid: boolean(value.valid),
    expires_at: string(value.expires_at),
  };
}
function parseExample(value: unknown): ImportedExample {
  if (!isRecord(value) || !Array.isArray(value.tools)) return invalid("processed example tools");
  return parseCatalogExample(value);
}
function parseDiagnostic(value: unknown): Diagnostic {
  if (!isRecord(value)) return invalid("diagnostic");
  return {
    category: string(value.category),
    message: string(value.message),
    source_index: nullableNumber(value.source_index),
    line: nullableNumber(value.line),
    column: nullableNumber(value.column),
    field_path: nullableString(value.field_path),
  };
}
function parseJob(value: unknown): ImportJob {
  if (!isRecord(value) || !isRecord(value.spec)) return invalid("import job");
  const states: ImportJobState[] = [
    "queued",
    "running",
    "cancelling",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
  ];
  if (typeof value.state !== "string" || !states.includes(value.state as ImportJobState)) return invalid("job state");
  const spec = value.spec;
  if (!Array.isArray(spec.segment_keys) || !Array.isArray(spec.tags)) return invalid("job specification");
  return {
    id: string(value.id),
    name: string(value.name),
    state: value.state as ImportJobState,
    phase: string(value.phase),
    rows_loaded: number(value.rows_loaded),
    rows_kept: number(value.rows_kept),
    rows_dropped: number(value.rows_dropped),
    created_at: string(value.created_at),
    updated_at: string(value.updated_at),
    dataset_id: nullableString(value.dataset_id),
    error: value.error === null ? null : parseDiagnostic(value.error),
    spec: {
      source: parseSource(spec.source),
      row_limit: number(spec.row_limit),
      resolved_sha: string(spec.resolved_sha),
      source_code: string(spec.source_code),
      source_hash: string(spec.source_hash),
      segment_keys: spec.segment_keys.map(string),
      tags: spec.tags.map(string),
      processor_contract_version: string(spec.processor_contract_version),
      runtime_policy_version: string(spec.runtime_policy_version),
      runtime_version: string(spec.runtime_version),
    },
  };
}
function parseSource(value: unknown): SourceCoordinates {
  if (!isRecord(value) || value.kind !== "hf_dataset") return invalid("source");
  return {
    kind: "hf_dataset",
    repo_id: string(value.repo_id),
    config: nullableString(value.config),
    split: string(value.split),
    revision: string(value.revision),
  };
}
function jsonObject(value: unknown): Record<string, JsonValue> {
  const parsed = jsonValue(value);
  if (isRecord(parsed)) return parsed as Record<string, JsonValue>;
  return invalid("JSON object");
}
function jsonValue(value: unknown): JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.map(jsonValue);
  if (isRecord(value)) return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, jsonValue(item)]));
  return invalid("JSON value");
}
function string(value: unknown): string {
  if (typeof value === "string") return value;
  return invalid("string");
}
function number(value: unknown): number {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) return value;
  return invalid("number");
}
function nullableNumber(value: unknown): number | null {
  return value === null ? null : number(value);
}
function nullableString(value: unknown): string | null {
  return value === null ? null : string(value);
}
function boolean(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  return invalid("boolean");
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function invalid(shape: string): never {
  throw new CatalogError(`The import API returned an unexpected ${shape}.`, 500);
}
function errorMessage(value: unknown): string {
  if (!isRecord(value)) return "The dataset import request failed.";
  const detail = value.detail;
  if (typeof detail === "string") return detail;
  if (isRecord(detail) && typeof detail.message === "string") return detail.message;
  return "The dataset import request failed.";
}
