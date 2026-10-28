import { CatalogError } from "../../shared/catalog-error";
import type { ToolCall, TextPart, MediaPart } from "../../api-schema";
import type { ExamplePage, ExampleRow } from "../../catalog-types";
import { formatDate } from "../../shared/format";
export const PAGE_SIZE = 50;
export type Position = { offset: number; row: number | null };

export function selectedRow(page: ExamplePage, requested: string | null): number | null {
  const row = Number(requested);
  if (requested !== null && Number.isInteger(row) && row > page.offset && row <= page.offset + page.examples.length) {
    return row;
  }
  return page.examples.length === 0 ? null : page.offset + 1;
}

export function matches(example: ExampleRow, query: string, facetKey: string | null, facet: string | null): boolean {
  if (facet !== null && facetKey !== null && example.segments[facetKey] !== facet) return false;
  const needle = query.trim().toLowerCase();
  if (needle === "" || /^\d+$/.test(needle)) return true;
  const haystack = [
    preview(example),
    ...Object.values(example.segments),
    typeof example.expected_output === "string" ? example.expected_output : formatValue(example.expected_output),
  ]
    .join("\n")
    .toLowerCase();
  return haystack.includes(needle);
}

export function facetValues(examples: ExampleRow[], key: string | null): string[] {
  if (key === null) return [];
  return [
    ...new Set(
      examples.map((example) => example.segments[key]).filter((value): value is string => value !== undefined),
    ),
  ].sort((a, b) => a.localeCompare(b));
}

export function preview(example: ExampleRow): string {
  const message =
    example.conversation.find((item) => item.role === "user") ??
    example.conversation.find((item) => item.role !== "system");
  const text = message === undefined ? null : messageText(message.content);
  return text === null ? "No user message" : text.replace(/\s+/g, " ").slice(0, 200);
}

export function callText(call: ToolCall): string {
  return `${call.function.name}(${JSON.stringify(call.function.arguments)})`;
}

export function isJsonText(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return false;
  try {
    JSON.parse(trimmed);
    return true;
  } catch {
    return false;
  }
}

export function messageText(content: string | Array<TextPart | MediaPart> | null | undefined): string | null {
  if (typeof content === "string") return content === "" ? null : content;
  if (content == null) return null;
  const parts = content.map((part) => ("text" in part ? part.text : `[${part.type}]`)).filter((part) => part !== "");
  return parts.length === 0 ? null : parts.join("\n");
}

export function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2) ?? "";
}

export function formatCreated(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${formatDate(value)} ${date.toISOString().slice(11, 16)} UTC`;
}

export function readPosition(params: URLSearchParams): Position {
  const row = readIndex(params.get("row"), "Row", 1);
  const offsetText = params.get("offset");
  if (offsetText !== null && offsetText !== "") {
    return { offset: readIndex(offsetText, "Offset", 0) ?? 0, row };
  }
  return { offset: row === null ? 0 : Math.floor((row - 1) / PAGE_SIZE) * PAGE_SIZE, row };
}

export function readIndex(value: string | null, label: string, minimum: number): number | null {
  if (value === null || value === "") return null;
  if (!/^\d+$/.test(value)) throw new CatalogError(`${label} must be a whole number.`, 422);
  const index = Number(value);
  if (!Number.isSafeInteger(index)) throw new CatalogError(`${label} must be a safe whole number.`, 422);
  if (index < minimum) throw new CatalogError(`${label} must be at least ${minimum}.`, 422);
  return index;
}
