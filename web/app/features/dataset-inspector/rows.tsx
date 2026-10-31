import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import type { ExamplePage } from "../../catalog-types";
import { useShortcut } from "../../shared/browser";
import { formatCount } from "../../shared/format";
import { PAGE_SIZE, matches, facetValues, preview } from "./model";

export function RowIndex({
  go,
  page,
  selected,
}: {
  go: (row: number) => void;
  page: ExamplePage;
  selected: number | null;
}) {
  const segmentId = useId();
  const valueId = useId();
  const listRef = useRef<HTMLOListElement>(null);
  const filterRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [facet, setFacet] = useState<string | null>(null);
  const start = page.examples.length === 0 ? 0 : page.offset + 1;
  const end = page.offset + page.examples.length;
  const hasPrevious = page.offset > 0;
  const hasNext = page.offset + PAGE_SIZE < page.total;
  const facetKeys = [...new Set(page.examples.flatMap((example) => Object.keys(example.segments)))];
  const [facetKey, setFacetKey] = useState<string | null>(() => facetKeys[0] ?? null);
  const facets = facetValues(page.examples, facetKey);
  const items = page.examples
    .map((example, index) => ({ example, row: page.offset + index + 1 }))
    .filter(({ example }) => matches(example, query, facetKey, facet));

  useShortcut("/", () => filterRef.current?.focus());

  // biome-ignore lint/correctness/useExhaustiveDependencies: Selection and filtering change the DOM target to reveal.
  useEffect(() => {
    listRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: "nearest" });
  }, [selected, query, facet]);

  return (
    <section aria-labelledby="rows-heading" className="row-index">
      <p className="page-range">
        {formatCount(start)}–{formatCount(end)} of {formatCount(page.total)}
      </p>
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
          <label htmlFor="row-search">Search this page</label>
          <input
            id="row-search"
            aria-label="Filter rows or go to a row number"
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter or row #"
            ref={filterRef}
            value={query}
          />
        </form>
      </div>
      {facetKeys.length > 0 ? (
        <div className="segment-filters">
          <div className="segment-field">
            <label htmlFor={segmentId}>Segment</label>
            <select
              id={segmentId}
              value={facetKey ?? ""}
              onChange={(event) => {
                setFacetKey(event.target.value || null);
                setFacet(null);
              }}
            >
              {facetKeys.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </div>
          <div className="segment-field">
            <label htmlFor={valueId}>Value</label>
            <select
              id={valueId}
              aria-label="Segment value"
              value={facet === null ? "all" : `value:${facet}`}
              onChange={(event) => setFacet(event.target.value === "all" ? null : event.target.value.slice(6))}
            >
              <option value="all">All values</option>
              {facets.map((value) => (
                <option key={value} value={`value:${value}`}>
                  {value === "" ? "(Empty value)" : value}
                </option>
              ))}
            </select>
          </div>
          <p className="hint">Values and filters apply to this page only.</p>
          <p className="hint" role="status">
            {formatCount(items.length)} of {formatCount(page.examples.length)} examples match
          </p>
        </div>
      ) : null}
      <ol className="row-items" ref={listRef}>
        {items.length === 0 ? <li className="hint row-empty">No rows on this page match.</li> : null}
        {items.map(({ example, row }) => (
          <li key={row}>
            <Link
              aria-current={row === selected ? "true" : undefined}
              onClick={(event) => {
                event.preventDefault();
                go(row);
              }}
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
      <nav aria-label="Row pages" className="pager">
        <PageLink disabled={!hasPrevious} label="Previous page" to={`?offset=${Math.max(0, page.offset - PAGE_SIZE)}`}>
          <ChevronLeft aria-hidden="true" size={15} strokeWidth={1.75} />
        </PageLink>
        <PageLink disabled={!hasNext} label="Next page" to={`?offset=${page.offset + PAGE_SIZE}`}>
          <ChevronRight aria-hidden="true" size={15} strokeWidth={1.75} />
        </PageLink>
      </nav>
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
      <button disabled aria-label={label} className="icon-button is-disabled" type="button">
        {children}
      </button>
    );
  }
  return (
    <Link aria-label={label} className="icon-button" to={to}>
      {children}
    </Link>
  );
}
