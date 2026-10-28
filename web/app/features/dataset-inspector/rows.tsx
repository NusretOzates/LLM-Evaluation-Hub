import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
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
  const listRef = useRef<HTMLOListElement>(null);
  const filterRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [facet, setFacet] = useState<string | null>(null);
  const start = page.examples.length === 0 ? 0 : page.offset + 1;
  const end = page.offset + page.examples.length;
  const hasPrevious = page.offset > 0;
  const hasNext = page.offset + PAGE_SIZE < page.total;
  const facetKey = page.examples[0] === undefined ? null : (Object.keys(page.examples[0].segments)[0] ?? null);
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
          <PageLink
            disabled={!hasPrevious}
            label="Previous page"
            to={`?offset=${Math.max(0, page.offset - PAGE_SIZE)}`}
          >
            <ChevronLeft aria-hidden="true" size={15} strokeWidth={1.75} />
          </PageLink>
          <PageLink disabled={!hasNext} label="Next page" to={`?offset=${page.offset + PAGE_SIZE}`}>
            <ChevronRight aria-hidden="true" size={15} strokeWidth={1.75} />
          </PageLink>
        </nav>
      </div>
      {facets.length > 1 && facets.length <= 8 ? (
        <fieldset className="facet-bar" aria-label={facetKey ?? "Segments"}>
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
        </fieldset>
      ) : null}
      <ol className="row-items" ref={listRef}>
        {items.length === 0 ? <li className="hint row-empty">No rows on this page match.</li> : null}
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
