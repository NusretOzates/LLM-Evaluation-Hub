import type * as Schema from "../../api-schema";
import type { Output } from "../inference/api";
import type { ExampleRow, ToolDefinition } from "../../catalog-types";
export type JsonValue = Schema.JsonValue;

export type ImportedExample = ExampleRow & { tools: ToolDefinition[] };
export type SourceCoordinates = Schema.SourceSpec & {
  kind: "hf_dataset";
  config: string | null;
  split: string;
  revision: string;
};
export type SourceColumn = Schema.SourceColumn;
export type ImportLimits = Schema.ImportLimits & { max_rows: number; sample_rows: number; max_source_bytes: number };
export type ImportSources = Omit<Schema.SourcesView, "sources" | "limits"> & {
  sources: Array<Schema.SourceChoice & { kind: "hf_dataset"; label: string }>;
  limits: ImportLimits;
};
export type SourceSample = Schema.SampleView & { source: SourceCoordinates };
export type Diagnostic = Schema.Diagnostic & {
  source_index: number | null;
  line: number | null;
  column: number | null;
  field_path: string | null;
};
export type PreviewRow = Omit<Schema.PreviewRow, "example" | "error"> & {
  example: ImportedExample | null;
  error: Diagnostic | null;
};
export type DatasetPreview = Omit<Schema.PreviewView, "id" | "rows"> & { id: string | null; rows: PreviewRow[] };
export type ImportSpecification = Schema.ImportSpec & {
  output_format: Output;
  source: SourceCoordinates;
  tags: string[];
  processor_contract_version: NonNullable<Schema.ImportSpec["processor_contract_version"]>;
  runtime_policy_version: NonNullable<Schema.ImportSpec["runtime_policy_version"]>;
};
export type ImportJob = Schema.JobView & {
  dataset_id: string | null;
  error: Diagnostic | null;
  spec: ImportSpecification;
};
export type ImportJobState = Schema.JobView["state"];
export type { ToolDefinition };
