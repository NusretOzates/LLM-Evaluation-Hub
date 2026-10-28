import type * as Schema from "./api-schema";

export type Dataset = Schema.DatasetView;
export type TagNode = Omit<Schema.TagNode, "children"> & { children: Record<string, TagNode> };
export type TagBranch = { children: Record<string, TagBranch> };
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type ToolDefinition = Schema.ToolDefinition & {
  function: { name: string; description?: string; parameters: { [key: string]: JsonValue }; strict?: boolean };
};
export type Message =
  | (Schema.SystemMessage & { role: "system" })
  | (Schema.UserMessage & { role: "user" })
  | (Schema.AssistantMessage & { role: "assistant" })
  | (Schema.ToolMessage & { role: "tool" });
export type ExampleRow = Omit<Required<Schema.ProcessedExample>, "conversation" | "tools"> & {
  conversation: Message[];
  tools?: ToolDefinition[];
};
export type ExamplePage = Omit<Schema.ExamplePage, "examples"> & { examples: ExampleRow[] };
