import { Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Copy, List, PanelRight, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useFetcher, useNavigate, useSearchParams } from "react-router";

import {
  addTags,
  CatalogError,
  flattenTags,
  getDataset,
  listExamples,
  listTags,
  removeTags,
  type Dataset,
  type ExamplePage,
  type ExampleRow,
  type Message,
  type TagNode,
} from "../catalog";
import { CatalogAlert, useShortcut, useStoredFlag } from "../shell";
import type { Route } from "./+types/dataset";
import { formatCount, formatDate } from "./datasets";

const PAGE_SIZE = 50;

type ActionData = { error: string } | { ok: true };

type Position = { offset: number; row: number | null };

export function meta({ params }: Route.MetaArgs) {
  const name = "name" in params ? params.name : undefined;
  return [{ title: name ? `${name} · Evaluation hub` : "Dataset · Evaluation hub" }];
}

export async function clientLoader({ params, request }: Route.ClientLoaderArgs) {
  const name = params.name;
  if (name === undefined || name === "") {
    throw new CatalogError("Dataset name is missing.", 404);
  }
  const { offset } = readPosition(new URL(request.url).searchParams);
  const [dataset, page, tags] = await Promise.all([
    getDataset(name),
    listExamples(name, offset, PAGE_SIZE),
    listTags(),
  ]);
  return { dataset, page, tags };
}

export function shouldRevalidate({
  currentUrl,
  defaultShouldRevalidate,
  formMethod,
  nextUrl,
}: {
  currentUrl: URL;
  defaultShouldRevalidate: boolean;
  formMethod?: string;
  nextUrl: URL;
}) {
  if (formMethod !== undefined || currentUrl.pathname !== nextUrl.pathname) return defaultShouldRevalidate;
  try {
    return readPosition(currentUrl.searchParams).offset !== readPosition(nextUrl.searchParams).offset;
  } catch {
    return defaultShouldRevalidate;
  }
}

export async function clientAction({ params, request }: Route.ClientActionArgs): Promise<ActionData> {
  const name = params.name;
  if (name === undefined || name === "") return { error: "Dataset name is missing." };
  const form = await request.formData();
  const path = String(form.get("path") ?? "");
  const intent = String(form.get("intent") ?? "");
  if (path === "") return { error: "Choose a tag." };
  try {
    if (intent === "detach") await removeTags(name, [path]);
    else await addTags(name, [path]);
  } catch (error) {
    if (error instanceof CatalogError) return { error: error.message };
    throw error;
  }
  return { ok: true };
}

export default function DatasetPage({ loaderData }: Route.ComponentProps) {
  const { dataset, page, tags } = loaderData;
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [showDetails, setShowDetails] = useStoredFlag("dataset-aside", false);
  const [showIndex, setShowIndex] = useStoredFlag("dataset-index", true);
  useShortcut("]", () => setShowDetails((value) => !value));
  useShortcut("\\", () => setShowIndex((value) => !value));
  const selected = selectedRow(page, params.get("row"));

  function go(row: number) {
    if (row < 1 || row > page.total) return;
    const offset = Math.floor((row - 1) / PAGE_SIZE) * PAGE_SIZE;
    navigate(`?offset=${offset}&row=${row}`, { replace: true, preventScrollReset: true });
  }

  return (
    <div className="page">
      <header className="topbar">
        <nav aria-label="Breadcrumb" className="crumbs">
          <Link to="/datasets">Datasets</Link>
          <ChevronRight aria-hidden="true" size={14} strokeWidth={1.75} />
          <h1>{dataset.name}</h1>
        </nav>
        <Summary dataset={dataset} />
        <button
          aria-label="Row list"
          aria-pressed={showIndex}
          className="icon-button topbar-toggle"
          onClick={() => setShowIndex((value) => !value)}
          title="Row list (\\)"
          type="button"
        >
          <List aria-hidden="true" size={15} strokeWidth={1.75} />
        </button>
        <button
          aria-label="Dataset details"
          aria-pressed={showDetails}
          className="icon-button"
          onClick={() => setShowDetails((value) => !value)}
          title="Dataset details (])"
          type="button"
        >
          <PanelRight aria-hidden="true" size={15} strokeWidth={1.75} />
        </button>
      </header>
      <div className="inspector" data-details={showDetails} data-index={showIndex}>
        {showIndex ? <RowIndex go={go} page={page} selected={selected} /> : null}
        <RowViewer go={go} page={page} selected={selected} />
        {showDetails ? (
          <aside aria-label="Dataset details" className="aside">
            <TagManager dataset={dataset} tags={tags} />
            <Details dataset={dataset} />
          </aside>
        ) : null}
      </div>
    </div>
  );
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  return (
    <div className="page">
      <header className="topbar">
        <nav aria-label="Breadcrumb" className="crumbs">
          <Link to="/datasets">Datasets</Link>
        </nav>
      </header>
      <div className="page-body">
        <CatalogAlert error={error} />
      </div>
    </div>
  );
}

function Summary({ dataset }: { dataset: Dataset }) {
  const percent = dataset.rows_loaded === 0 ? 0 : Math.round((dataset.rows_kept / dataset.rows_loaded) * 100);
  const loaded = `${formatCount(dataset.rows_loaded)} loaded${
    dataset.row_limit === null ? "" : ` (limit ${formatCount(dataset.row_limit)})`
  }`;
  return (
    <p className="summary">
      <span>
        <strong className="mono">{formatCount(dataset.rows_kept)}</strong> rows kept
      </span>
      <span>{formatCount(dataset.rows_dropped)} dropped</span>
      <span>{loaded}</span>
      <span>{percent}% retained</span>
    </p>
  );
}

function RowIndex({
  go,
  page,
  selected,
}: {
  go: (row: number) => void;
  page: ExamplePage;
  selected: number | null;
}) {
  const listRef = useRef<HTMLOListElement>(null);
  const filterRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [facet, setFacet] = useState<string | null>(null);
  const start = page.examples.length === 0 ? 0 : page.offset + 1;
  const end = page.offset + page.examples.length;
  const hasPrevious = page.offset > 0;
  const hasNext = page.offset + PAGE_SIZE < page.total;
  const facetKey = page.examples[0] === undefined ? null : Object.keys(page.examples[0].segments)[0] ?? null;
  const facets = facetValues(page.examples, facetKey);
  const items = page.examples
    .map((example, index) => ({ example, row: page.offset + index + 1 }))
    .filter(({ example }) => matches(example, query, facetKey, facet));

  useShortcut("/", () => filterRef.current?.focus());

  useEffect(() => {
    listRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: "nearest" });
  }, [selected, query, facet]);

  return (
    <section aria-labelledby="rows-heading" className="row-index">
      <div className="index-bar">
        <h2 className="sr-only" id="rows-heading">
          Rows
        </h2>
        <form
          className="jump"
          onSubmit={(event) => {
            event.preventDefault();
            const trimmed = query.trim();
            if (/^\d+$/.test(trimmed)) {
              go(Number(trimmed));
              setQuery("");
            }
          }}
        >
          <input
            aria-label="Filter rows or go to a row number"
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter or row #"
            ref={filterRef}
            value={query}
          />
        </form>
        <nav aria-label="Row pages" className="pager">
          <span className="sr-only">
            {formatCount(start)}–{formatCount(end)} of {formatCount(page.total)}
          </span>
          <PageLink disabled={!hasPrevious} label="Previous page" to={`?offset=${Math.max(0, page.offset - PAGE_SIZE)}`}>
            <ChevronLeft aria-hidden="true" size={15} strokeWidth={1.75} />
          </PageLink>
          <PageLink disabled={!hasNext} label="Next page" to={`?offset=${page.offset + PAGE_SIZE}`}>
            <ChevronRight aria-hidden="true" size={15} strokeWidth={1.75} />
          </PageLink>
        </nav>
      </div>
      {facets.length > 1 && facets.length <= 8 ? (
        <div className="facet-bar" role="group" aria-label={facetKey ?? "Segments"}>
          <button aria-pressed={facet === null} className="facet" onClick={() => setFacet(null)} type="button">
            All
          </button>
          {facets.map((value) => (
            <button
              aria-pressed={facet === value}
              className="facet"
              key={value}
              onClick={() => setFacet((current) => (current === value ? null : value))}
              type="button"
            >
              {value}
            </button>
          ))}
        </div>
      ) : null}
      <ol className="row-items" ref={listRef}>
        {items.length === 0 ? (
          <li className="hint row-empty">No rows on this page match.</li>
        ) : null}
        {items.map(({ example, row }) => (
          <li key={row}>
            <Link
              aria-current={row === selected ? "true" : undefined}
              className="row-item"
              preventScrollReset
              replace
              to={`?offset=${page.offset}&row=${row}`}
            >
              <span className="row-item-head">
                <span className="mono">#{row}</span>
                <span className="row-item-meta mono">{Object.values(example.segments).join(" · ")}</span>
              </span>
              <span className="row-item-preview">{preview(example)}</span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

function RowViewer({
  go,
  page,
  selected,
}: {
  go: (row: number) => void;
  page: ExamplePage;
  selected: number | null;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [raw, setRaw] = useState(false);
  const [copied, setCopied] = useState(false);
  const example = selected === null ? undefined : page.examples[selected - page.offset - 1];

  useShortcut("j", () => {
    if (selected !== null) go(selected + 1);
  });
  useShortcut("k", () => {
    if (selected !== null) go(selected - 1);
  });

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: 0 });
    setCopied(false);
  }, [selected]);

  if (example === undefined || selected === null) {
    return (
      <section aria-label="Row" className="viewer">
        <div className="viewer-empty">
          {page.total === 0 ? (
            <p>This dataset has no stored rows.</p>
          ) : (
            <p>
              This page is past the last row. <Link to="?offset=0">Go to the first row.</Link>
            </p>
          )}
        </div>
      </section>
    );
  }

  const segments = Object.entries(example.segments);
  const extras = Object.entries(example.extras);
  return (
    <section aria-labelledby="row-title" className="viewer">
      <header className="viewer-bar">
        <h2 id="row-title">
          Row <span className="mono">{formatCount(selected)}</span>
          <span className="muted"> of {formatCount(page.total)}</span>
        </h2>
        {segments.length === 0 ? null : (
          <dl className="segments">
            {segments.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd className="mono">{value}</dd>
              </div>
            ))}
          </dl>
        )}
        <div className="viewer-actions">
          <button
            aria-pressed={raw}
            className="button-ghost button-small"
            onClick={() => setRaw((value) => !value)}
            type="button"
          >
            JSON
          </button>
          <button
            className="button-ghost button-small"
            onClick={() => {
              void navigator.clipboard.writeText(JSON.stringify(example, null, 2)).then(() => setCopied(true));
            }}
            type="button"
          >
            {copied ? (
              <Check aria-hidden="true" size={13} strokeWidth={2} />
            ) : (
              <Copy aria-hidden="true" size={13} strokeWidth={1.75} />
            )}
            {copied ? "Copied" : "Copy"}
          </button>
          <span className="divider" />
          <button
            aria-label="Previous row"
            className="icon-button"
            disabled={selected <= 1}
            onClick={() => go(selected - 1)}
            title="Previous row (k)"
            type="button"
          >
            <ChevronUp aria-hidden="true" size={15} strokeWidth={1.75} />
          </button>
          <button
            aria-label="Next row"
            className="icon-button"
            disabled={selected >= page.total}
            onClick={() => go(selected + 1)}
            title="Next row (j)"
            type="button"
          >
            <ChevronDown aria-hidden="true" size={15} strokeWidth={1.75} />
          </button>
        </div>
      </header>
      <div className="viewer-body" ref={bodyRef}>
        {raw ? (
          <pre className="raw mono">{JSON.stringify(example, null, 2)}</pre>
        ) : (
          <>
            <article aria-label="Conversation" className="example">
              {example.conversation.map((message, turn) => (
                <MessageView key={`${message.role}-${turn}`} message={message} />
              ))}
              {example.expected_output === null || example.expected_output === undefined ? null : (
                <div className="expected">
                  <span className="block-label">Expected</span>
                  {typeof example.expected_output === "string" ? (
                    <p>{example.expected_output}</p>
                  ) : (
                    <pre className="mono">{formatValue(example.expected_output)}</pre>
                  )}
                </div>
              )}
            </article>
            {extras.length === 0 ? null : (
              <section aria-labelledby="extras-heading" className="extras-card">
                <h3 id="extras-heading">Extras</h3>
                <dl>
                  {extras.map(([key, value]) => (
                    <div key={key}>
                      <dt className="mono">{key}</dt>
                      <dd>{typeof value === "string" ? <p>{value}</p> : <pre className="mono">{formatValue(value)}</pre>}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function TagManager({ dataset, tags }: { dataset: Dataset; tags: Record<string, TagNode> }) {
  const fetcher = useFetcher<ActionData>();
  const available = flattenTags(tags)
    .map((node) => node.path)
    .filter((path) => !dataset.tags.includes(path));
  const error = fetcher.data !== undefined && "error" in fetcher.data ? fetcher.data.error : null;
  const busy = fetcher.state !== "idle";
  return (
    <section aria-labelledby="dataset-tags" className="aside-section">
      <h2 id="dataset-tags">Tags</h2>
      {dataset.tags.length === 0 ? (
        <p className="hint">This dataset has no tags.</p>
      ) : (
        <ul className="tag-list">
          {dataset.tags.map((path) => (
            <li key={path}>
              <span className="mono">{path}</span>
              <fetcher.Form method="post">
                <input name="path" type="hidden" value={path} />
                <button
                  aria-label={`Remove ${path}`}
                  className="icon-button"
                  disabled={busy}
                  name="intent"
                  type="submit"
                  value="detach"
                >
                  <X aria-hidden="true" size={13} strokeWidth={1.75} />
                </button>
              </fetcher.Form>
            </li>
          ))}
        </ul>
      )}
      {available.length === 0 ? null : (
        <fetcher.Form className="tag-add" method="post">
          <select aria-label="Tag to add" defaultValue={available[0]} key={available.join("|")} name="path">
            {available.map((path) => (
              <option key={path} value={path}>
                {path}
              </option>
            ))}
          </select>
          <button className="button-ghost" disabled={busy} name="intent" type="submit" value="attach">
            Add
          </button>
        </fetcher.Form>
      )}
      {error === null ? null : (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

function Details({ dataset }: { dataset: Dataset }) {
  const rows: Array<[string, string | null]> = [
    ["Source", dataset.source_type],
    ["Repository", dataset.repo_id],
    ["Config", dataset.config],
    ["Split", dataset.split],
    ["Revision", dataset.revision],
    ["Commit", dataset.resolved_sha === null ? null : dataset.resolved_sha.slice(0, 12)],
    ["Segments", dataset.segment_keys.length === 0 ? null : dataset.segment_keys.join(", ")],
    ["Processor", dataset.processor_id],
    ["Created", formatCreated(dataset.created_at)],
  ];
  return (
    <section aria-labelledby="dataset-details" className="aside-section">
      <h2 id="dataset-details">Details</h2>
      <dl className="details">
        {rows
          .filter((row): row is [string, string] => row[1] !== null && row[1] !== "")
          .map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd className="mono">{value}</dd>
            </div>
          ))}
      </dl>
    </section>
  );
}

function PageLink({
  children,
  disabled,
  label,
  to,
}: {
  children: ReactNode;
  disabled: boolean;
  label: string;
  to: string;
}) {
  if (disabled) {
    return (
      <span aria-disabled="true" aria-label={label} className="icon-button is-disabled" role="link">
        {children}
      </span>
    );
  }
  return (
    <Link aria-label={label} className="icon-button" to={to}>
      {children}
    </Link>
  );
}

function MessageView({ message }: { message: Message }) {
  const text = messageText(message.content);
  const toolCalls = Array.isArray(message.tool_calls) && message.tool_calls.length > 0 ? message.tool_calls : null;
  const structured = message.role === "tool" && text !== null && isJsonText(text);
  if (message.role === "system" && text === null && toolCalls === null) return null;
  if (message.role === "system" && text !== null) {
    return (
      <details className="system-fold">
        <summary>
          <span className="turn-role mono">system</span>
          <span className="system-preview">{text.replace(/\s+/g, " ")}</span>
        </summary>
        <p>{text}</p>
      </details>
    );
  }
  return (
    <div className="turn" data-role={message.role}>
      <span className="turn-role mono">
        {message.role}
        {typeof message.name === "string" ? <span className="turn-name">{message.name}</span> : null}
      </span>
      <div className="turn-body">
        {text === null && toolCalls === null ? <p className="turn-empty">No content</p> : null}
        {typeof message.thinking === "string" && message.thinking !== "" ? (
          <details className="thinking">
            <summary>Thinking</summary>
            <p>{message.thinking}</p>
          </details>
        ) : null}
        {text === null ? null : structured ? <code className="call mono">{text}</code> : <p>{text}</p>}
        {toolCalls === null
          ? null
          : toolCalls.map((call, index) => (
              <code className="call mono" key={index}>
                {callText(call)}
              </code>
            ))}
      </div>
    </div>
  );
}

function selectedRow(page: ExamplePage, requested: string | null): number | null {
  const row = Number(requested);
  if (requested !== null && Number.isInteger(row) && row > page.offset && row <= page.offset + page.examples.length) {
    return row;
  }
  return page.examples.length === 0 ? null : page.offset + 1;
}

function matches(example: ExampleRow, query: string, facetKey: string | null, facet: string | null): boolean {
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

function facetValues(examples: ExampleRow[], key: string | null): string[] {
  if (key === null) return [];
  return [...new Set(examples.map((example) => example.segments[key]).filter((value): value is string => value !== undefined))].sort(
    (a, b) => a.localeCompare(b),
  );
}

function preview(example: ExampleRow): string {
  const message =
    example.conversation.find((item) => item.role === "user") ??
    example.conversation.find((item) => item.role !== "system");
  const text = message === undefined ? null : messageText(message.content);
  return text === null ? "No user message" : text.replace(/\s+/g, " ").slice(0, 200);
}

function callText(call: unknown): string {
  if (!isRecord(call) || !isRecord(call.function) || typeof call.function.name !== "string") {
    return formatValue(call);
  }
  return `${call.function.name}(${JSON.stringify(call.function.arguments ?? {})})`;
}

function isJsonText(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return false;
  try {
    JSON.parse(trimmed);
    return true;
  } catch {
    return false;
  }
}

function messageText(content: unknown): string | null {
  if (typeof content === "string") return content === "" ? null : content;
  if (content === null || content === undefined) return null;
  if (Array.isArray(content)) {
    const parts = content.map(partText).filter((part) => part !== "");
    return parts.length === 0 ? null : parts.join("\n");
  }
  return formatValue(content);
}

function partText(part: unknown): string {
  if (!isRecord(part)) return formatValue(part);
  if (part.type === "text" && typeof part.text === "string") return part.text;
  if (typeof part.type === "string") return `[${part.type}]`;
  return formatValue(part);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2) ?? "";
}

function formatCreated(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${formatDate(value)} ${date.toISOString().slice(11, 16)} UTC`;
}

function readPosition(params: URLSearchParams): Position {
  const row = readIndex(params.get("row"), "Row", 1);
  const offsetText = params.get("offset");
  if (offsetText !== null && offsetText !== "") {
    return { offset: readIndex(offsetText, "Offset", 0) ?? 0, row };
  }
  return { offset: row === null ? 0 : Math.floor((row - 1) / PAGE_SIZE) * PAGE_SIZE, row };
}

function readIndex(value: string | null, label: string, minimum: number): number | null {
  if (value === null || value === "") return null;
  if (!/^\d+$/.test(value)) throw new CatalogError(`${label} must be a whole number.`, 422);
  const index = Number(value);
  if (index < minimum) throw new CatalogError(`${label} must be at least ${minimum}.`, 422);
  return index;
}
