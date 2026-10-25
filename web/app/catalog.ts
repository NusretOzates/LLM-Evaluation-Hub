const API = "/api";

export class CatalogError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "CatalogError";
    this.status = status;
  }
}

export type TagNode = {
  path: string;
  children: Record<string, TagNode>;
};

export type TagBranch = {
  children: Record<string, TagBranch>;
};

export type Dataset = {
  id: string;
  name: string;
  created_at: string;
  processor_id: string;
  source_type: string;
  repo_id: string | null;
  config: string | null;
  split: string | null;
  revision: string | null;
  resolved_sha: string | null;
  row_limit: number | null;
  rows_loaded: number;
  rows_kept: number;
  rows_dropped: number;
  segment_keys: string[];
  tags: string[];
};

export type ExamplePage = {
  total: number;
  offset: number;
  limit: number;
  examples: ExampleRow[];
};

export type ExampleRow = {
  conversation: Message[];
  expected_output: unknown;
  extras: Record<string, unknown>;
  segments: Record<string, string>;
};

export type Message = {
  role: string;
  content?: unknown;
  tool_calls?: unknown;
  thinking?: unknown;
  tool_call_id?: unknown;
  name?: unknown;
};

export function tagForest(parent: string, name: string): Record<string, TagBranch> {
  const segments = parent === "" ? [name] : [...parent.split("/"), name];
  const root: Record<string, TagBranch> = {};
  let level = root;
  for (const segment of segments) {
    const branch: TagBranch = { children: {} };
    level[segment] = branch;
    level = branch.children;
  }
  return root;
}

export function flattenTags(forest: Record<string, TagNode>): TagNode[] {
  const nodes: TagNode[] = [];
  for (const name of Object.keys(forest).sort((a, b) => a.localeCompare(b))) {
    const node = forest[name];
    if (node === undefined) continue;
    nodes.push(node, ...flattenTags(node.children));
  }
  return nodes;
}

export function listTags(): Promise<Record<string, TagNode>> {
  return request("/tags", { method: "GET" }, parseTagForest);
}

export function createTags(forest: Record<string, TagBranch>): Promise<void> {
  return request("/tags", { method: "POST", body: JSON.stringify(forest) }, (value) => {
    parseTagForest(value);
  });
}

export function listDatasets(tag: string | null): Promise<Dataset[]> {
  const query = tag === null || tag === "" ? "" : `?tag=${encodeURIComponent(tag)}`;
  return request(`/datasets${query}`, { method: "GET" }, parseDatasets);
}

export function getDataset(name: string): Promise<Dataset> {
  return request(`/datasets/${encodeURIComponent(name)}`, { method: "GET" }, parseDataset);
}

export function addTags(name: string, paths: string[]): Promise<Dataset> {
  return request(
    `/datasets/${encodeURIComponent(name)}/tags`,
    { method: "POST", body: JSON.stringify({ paths }) },
    parseDataset,
  );
}

export function removeTags(name: string, paths: string[]): Promise<Dataset> {
  return request(
    `/datasets/${encodeURIComponent(name)}/tags`,
    { method: "DELETE", body: JSON.stringify({ paths }) },
    parseDataset,
  );
}

export function listExamples(name: string, offset: number, limit: number): Promise<ExamplePage> {
  const query = `?offset=${offset}&limit=${limit}`;
  return request(
    `/datasets/${encodeURIComponent(name)}/examples${query}`,
    { method: "GET" },
    parseExamplePage,
  );
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
  } catch {
    throw new CatalogError("The catalog API is not reachable.", 0);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new CatalogError(detailMessage(body), response.status);
  }
  return parse(body);
}

function detailMessage(body: unknown): string {
  if (!isRecord(body)) return "The catalog request failed.";
  const { detail } = body;
  if (typeof detail === "string" && detail !== "") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) =>
      isRecord(item) && typeof item.msg === "string" && item.msg !== "" ? [item.msg] : [],
    );
    if (messages.length > 0) return messages.join(" ");
  }
  return "The catalog request failed.";
}

function parseTagForest(value: unknown): Record<string, TagNode> {
  if (!isRecord(value)) throw new CatalogError("The catalog returned an unexpected tag tree.", 500);
  const forest: Record<string, TagNode> = {};
  for (const [name, node] of Object.entries(value)) {
    if (!isRecord(node) || typeof node.path !== "string") {
      throw new CatalogError("The catalog returned an unexpected tag tree.", 500);
    }
    forest[name] = { path: node.path, children: parseTagForest(node.children ?? {}) };
  }
  return forest;
}

function parseDatasets(value: unknown): Dataset[] {
  if (!Array.isArray(value)) throw new CatalogError("The catalog returned an unexpected dataset list.", 500);
  return value.map(parseDataset);
}

function parseDataset(value: unknown): Dataset {
  if (!isRecord(value)) throw new CatalogError("The catalog returned an unexpected dataset.", 500);
  return {
    id: expectString(value.id),
    name: expectString(value.name),
    created_at: expectString(value.created_at),
    processor_id: expectString(value.processor_id),
    source_type: expectString(value.source_type),
    repo_id: expectNullableString(value.repo_id),
    config: expectNullableString(value.config),
    split: expectNullableString(value.split),
    revision: expectNullableString(value.revision),
    resolved_sha: expectNullableString(value.resolved_sha),
    row_limit: expectNullableNumber(value.row_limit),
    rows_loaded: expectNumber(value.rows_loaded),
    rows_kept: expectNumber(value.rows_kept),
    rows_dropped: expectNumber(value.rows_dropped),
    segment_keys: expectStringArray(value.segment_keys),
    tags: expectStringArray(value.tags),
  };
}

function parseExamplePage(value: unknown): ExamplePage {
  if (!isRecord(value) || !Array.isArray(value.examples)) {
    throw new CatalogError("The catalog returned an unexpected example page.", 500);
  }
  return {
    total: expectNumber(value.total),
    offset: expectNumber(value.offset),
    limit: expectNumber(value.limit),
    examples: value.examples.map(parseExample),
  };
}

function parseExample(value: unknown): ExampleRow {
  if (!isRecord(value) || !Array.isArray(value.conversation)) {
    throw new CatalogError("The catalog returned an unexpected example.", 500);
  }
  return {
    conversation: value.conversation.map(parseMessage),
    expected_output: value.expected_output ?? null,
    extras: isRecord(value.extras) ? value.extras : {},
    segments: parseSegments(value.segments),
  };
}

function parseMessage(value: unknown): Message {
  if (!isRecord(value) || typeof value.role !== "string") {
    throw new CatalogError("The catalog returned an unexpected message.", 500);
  }
  return {
    role: value.role,
    content: value.content,
    tool_calls: value.tool_calls,
    thinking: value.thinking,
    tool_call_id: value.tool_call_id,
    name: value.name,
  };
}

function parseSegments(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  const segments: Record<string, string> = {};
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === "string") segments[key] = item;
  }
  return segments;
}

function expectString(value: unknown): string {
  if (typeof value !== "string") throw new CatalogError("The catalog returned an unexpected dataset.", 500);
  return value;
}

function expectNullableString(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  return expectString(value);
}

function expectNumber(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new CatalogError("The catalog returned an unexpected dataset.", 500);
  }
  return value;
}

function expectNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  return expectNumber(value);
}

function expectStringArray(value: unknown): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new CatalogError("The catalog returned an unexpected dataset.", 500);
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
