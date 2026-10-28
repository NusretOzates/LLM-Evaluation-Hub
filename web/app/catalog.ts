import { CatalogError } from "./shared/catalog-error";
import { detailMessage, parseDataset, parseDatasets, parseExamplePage, parseTagForest } from "./catalog-parsers";
import type { Dataset, ExamplePage, TagBranch, TagNode } from "./catalog-types";
export { CatalogError } from "./shared/catalog-error";
export type { Dataset, ExamplePage, ExampleRow, Message, TagBranch, TagNode } from "./catalog-types";
const API = "/api";

export function tagForest(parent: string, name: string): Record<string, TagBranch> {
  const segments = parent === "" ? [name] : [...parent.split("/"), name];
  const root: Record<string, TagBranch> = Object.create(null);
  let level = root;
  for (const segment of segments) {
    const branch: TagBranch = { children: Object.create(null) };
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

export function listTags(signal?: AbortSignal): Promise<Record<string, TagNode>> {
  return request("/tags", { method: "GET", signal }, parseTagForest);
}

export function createTags(forest: Record<string, TagBranch>): Promise<void> {
  return request("/tags", { method: "POST", body: JSON.stringify(forest) }, (value) => {
    parseTagForest(value);
  });
}

export function listDatasets(tag: string | null, signal?: AbortSignal): Promise<Dataset[]> {
  const query = tag === null || tag === "" ? "" : `?tag=${encodeURIComponent(tag)}`;
  return request(`/datasets${query}`, { method: "GET", signal }, parseDatasets);
}

export function getDataset(name: string, signal?: AbortSignal): Promise<Dataset> {
  return request(`/dataset-ids/${encodeURIComponent(name)}`, { method: "GET", signal }, parseDataset);
}

export function addTags(name: string, paths: string[]): Promise<Dataset> {
  return request(
    `/dataset-ids/${encodeURIComponent(name)}/tags`,
    { method: "POST", body: JSON.stringify({ paths }) },
    parseDataset,
  );
}

export function removeTags(name: string, paths: string[]): Promise<Dataset> {
  return request(
    `/dataset-ids/${encodeURIComponent(name)}/tags`,
    { method: "DELETE", body: JSON.stringify({ paths }) },
    parseDataset,
  );
}

export function listExamples(name: string, offset: number, limit: number, signal?: AbortSignal): Promise<ExamplePage> {
  const query = `?offset=${offset}&limit=${limit}`;
  return request(
    `/dataset-ids/${encodeURIComponent(name)}/examples${query}`,
    { method: "GET", signal },
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
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new CatalogError("The catalog API is not reachable.", 0);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new CatalogError(detailMessage(body), response.status);
  }
  return parse(body);
}
