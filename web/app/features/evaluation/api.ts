import type { JsonValue } from "../../catalog-types";
import type * as Schema from "../../api-schema";

export type Metric = Required<Schema.Metric>;
export type Definition = Omit<Required<Schema.Definition>, "method_config" | "metrics"> & {
  method_config: Record<string, JsonValue>;
  metrics: Metric[];
};
export type Evaluation = {
  id: string;
  source_inference_run_id: string;
  state: string;
  created_at: string;
  completed: number;
  total: number;
  error: string | null;
  settings: Definition;
  datasets: { dataset_id: string; name: string; rows_kept: number; tags: string[] }[];
};
export type Summary = {
  groups: {
    name: string | null;
    selected: number;
    scored: number;
    pending: number;
    failed: number;
    source_ineligible: number;
    coverage: number;
    means: Record<string, number | null>;
  }[];
  partial: boolean;
};
export type Result = {
  dataset_id: string;
  ordinal: number;
  source_index: number;
  status: string | null;
  stage: string | null;
  result: JsonValue;
  scores: Record<string, number> | null;
  evidence: JsonValue;
  error: string | null;
};
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, headers: { "Content-Type": "application/json" } });
  if (!response.ok) {
    const body: unknown = await response.json();
    const detail = typeof body === "object" && body !== null && "detail" in body ? body.detail : null;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((item) =>
                typeof item === "object" && item !== null && "msg" in item ? String(item.msg) : "Invalid value",
              )
              .join("; ")
          : "Request failed";
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
export const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
