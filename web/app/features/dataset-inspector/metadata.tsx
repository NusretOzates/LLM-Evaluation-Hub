import { X } from "lucide-react";
import { useFetcher } from "react-router";
import { flattenTags } from "../../catalog";
import type { Dataset, TagNode } from "../../catalog-types";
import { formatCount } from "../../shared/format";
import { formatCreated } from "./model";
type ActionData = { error: string } | { ok: true };

export function Summary({ dataset }: { dataset: Dataset }) {
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

export function TagManager({ dataset, tags }: { dataset: Dataset; tags: Record<string, TagNode> }) {
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

export function Details({ dataset }: { dataset: Dataset }) {
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
