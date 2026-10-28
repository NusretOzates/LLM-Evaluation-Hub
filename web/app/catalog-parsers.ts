import { CatalogError } from "./shared/catalog-error";
import type { Dataset, ExamplePage, ExampleRow, Message, TagNode, ToolDefinition } from "./catalog-types";
import type { JsonValue, MediaPart, TextPart, ToolCall } from "./api-schema";

export function detailMessage(body: unknown): string {
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

export function parseTagForest(value: unknown): Record<string, TagNode> {
  if (!isRecord(value)) throw new CatalogError("The catalog returned an unexpected tag tree.", 500);
  const forest: Record<string, TagNode> = Object.create(null);
  for (const [name, node] of Object.entries(value)) {
    if (!isRecord(node) || typeof node.path !== "string") {
      throw new CatalogError("The catalog returned an unexpected tag tree.", 500);
    }
    forest[name] = { path: node.path, children: parseTagForest(node.children) };
  }
  return forest;
}

export function parseDatasets(value: unknown): Dataset[] {
  if (!Array.isArray(value)) throw new CatalogError("The catalog returned an unexpected dataset list.", 500);
  return value.map(parseDataset);
}

export function parseDataset(value: unknown): Dataset {
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

export function parseExamplePage(value: unknown): ExamplePage {
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

export function parseExample(value: unknown): ExampleRow & { tools: ToolDefinition[] } {
  if (!isRecord(value) || !Array.isArray(value.conversation) || value.conversation.length === 0) {
    throw new CatalogError("The catalog returned an unexpected example.", 500);
  }
  return {
    conversation: value.conversation.map(parseMessage),
    expected_output: parseJson(value.expected_output),
    extras: parseJsonObject(value.extras),
    segments: parseSegments(value.segments),
    tools: value.tools === undefined ? [] : parseTools(value.tools),
  };
}

export function parseMessage(value: unknown): Message {
  if (!isRecord(value)) return invalid("message");
  switch (value.role) {
    case "system":
      return { role: "system", content: expectString(value.content) };
    case "user": {
      const content = typeof value.content === "string" ? value.content : parseParts(value.content);
      return { role: "user", content };
    }
    case "assistant": {
      const content = expectNullableString(value.content);
      const thinking = expectNullableString(value.thinking);
      if (!Array.isArray(value.tool_calls)) return invalid("tool calls");
      const tool_calls = value.tool_calls.map(parseToolCall);
      if (content === null && thinking === null && tool_calls.length === 0) return invalid("assistant message");
      return { role: "assistant", content, thinking, tool_calls };
    }
    case "tool":
      return {
        role: "tool",
        content: expectString(value.content),
        tool_call_id: expectNonemptyString(value.tool_call_id),
        name: expectNullableString(value.name),
      };
    default:
      return invalid("message role");
  }
}

function parseParts(value: unknown): Array<TextPart | MediaPart> {
  if (!Array.isArray(value) || value.length === 0) return invalid("content parts");
  return value.map((part): TextPart | MediaPart => {
    if (!isRecord(part)) return invalid("content part");
    if (part.type === "text") return { type: "text", text: expectString(part.text) };
    if (part.type !== "image" && part.type !== "video" && part.type !== "audio") return invalid("content part");
    const url = expectNullableString(part.url);
    const path = expectNullableString(part.path);
    if ((url === null) === (path === null) || url === "" || path === "") return invalid("media locator");
    return { type: part.type, url, path };
  });
}

function parseTools(value: unknown): import("./catalog-types").ToolDefinition[] {
  if (!Array.isArray(value)) return invalid("available tools");
  return value.map((item) => {
    if (!isRecord(item) || item.type !== "function" || !isRecord(item.function)) return invalid("tool definition");
    if (Object.keys(item).some((key) => key !== "type" && key !== "function")) return invalid("tool definition fields");
    const fn = item.function;
    if (Object.keys(fn).some((key) => !["name", "description", "parameters", "strict"].includes(key)))
      return invalid("tool function fields");
    const result: import("./catalog-types").ToolDefinition["function"] = {
      name: expectNonemptyString(fn.name),
      parameters: parseJsonObject(fn.parameters),
    };
    if ("description" in fn) result.description = expectString(fn.description);
    if ("strict" in fn) {
      if (typeof fn.strict !== "boolean") return invalid("tool strict flag");
      result.strict = fn.strict;
    }
    return { type: "function", function: result };
  });
}
function parseToolCall(value: unknown): ToolCall {
  if (!isRecord(value) || value.type !== "function" || !isRecord(value.function)) return invalid("tool call");
  return {
    id: expectNonemptyString(value.id),
    type: "function",
    function: {
      name: expectNonemptyString(value.function.name),
      arguments: parseJsonObject(value.function.arguments),
    },
  };
}

function parseJson(value: unknown): JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.map(parseJson);
  if (isRecord(value)) return parseJsonObject(value);
  return invalid("JSON value");
}

function parseJsonObject(value: unknown): Record<string, JsonValue> {
  if (!isRecord(value)) return invalid("JSON object");
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, parseJson(item)]));
}

function expectNonemptyString(value: unknown): string {
  const text = expectString(value);
  return text === "" ? invalid("nonempty string") : text;
}

function invalid(shape: string): never {
  throw new CatalogError(`The catalog returned an unexpected ${shape}.`, 500);
}

export function parseSegments(value: unknown): Record<string, string> {
  if (!isRecord(value)) return invalid("segments");
  const segments: Record<string, string> = Object.create(null);
  for (const [key, item] of Object.entries(value)) {
    segments[key] = expectString(item);
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
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
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
