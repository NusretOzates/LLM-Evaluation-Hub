import { DatasetMenu } from "../shared/dataset-menu";
import { Database, Plus } from "lucide-react";
import { Link, useRouteLoaderData, useSearchParams } from "react-router";
import { Button, FilterChip, SearchField } from "../shared/controls";
import { toggleTagPath } from "../shared/tag-picker";
import { DatasetTagFilter } from "../features/dataset-catalog-filter";

import { CatalogError, flattenTags, type Dataset } from "../catalog";
import { CatalogAlert } from "../shared/feedback";
import type { clientLoader as rootLoader } from "../root";
import { filterDatasets, parseCatalogFilters } from "../shared/catalog-view";
import { formatCount, formatDate } from "../shared/format";
import type { Route } from "./+types/datasets";

export function meta() {
  return [{ title: "Datasets · Evaluation hub" }];
}

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  const tag = new URL(request.url).searchParams.get("tag");
  return { tag };
}

export default function Datasets() {
  const [params, setParams] = useSearchParams();
  const catalog = useRouteLoaderData<typeof rootLoader>("root");
  if (catalog === undefined) throw new CatalogError("The catalog could not be loaded.", 500);
  const { query, tags } = parseCatalogFilters(params);
  const available = new Set(flattenTags(catalog.tags).map((node) => node.path));
  const datasets = filterDatasets(catalog.datasets, { query, tags }, available);
  function updateTags(next: string[]) {
    const updated = new URLSearchParams(params);
    updated.delete("tag");
    for (const tag of next) updated.append("tag", tag);
    setParams(updated);
  }
  function clearFilters() {
    const updated = new URLSearchParams(params);
    updated.delete("q");
    updated.delete("tag");
    setParams(updated);
  }
  return (
    <div className="page">
      <header className="topbar">
        <div className="title-row">
          <h1>Datasets</h1>
          <span className="title-count mono">{datasets.length}</span>
        </div>
        <div className="topbar-actions">
          <Link className="button-ghost button-small" to="/dataset-imports/new">
            <Plus aria-hidden="true" size={13} />
            Add dataset
          </Link>
        </div>
      </header>
      <div className="catalog-toolbar">
        <SearchField
          id="dataset-search"
          label="Search datasets"
          value={query}
          onChange={(value) => {
            const updated = new URLSearchParams(params);
            if (value) updated.set("q", value);
            else updated.delete("q");
            setParams(updated, { replace: true });
          }}
        />
        <DatasetTagFilter
          tags={catalog.tags}
          selected={tags}
          onChange={(path) => updateTags(toggleTagPath(tags, path))}
        />
      </div>
      {tags.length > 0 || query ? (
        <div className="catalog-chips">
          <span>Match all selected tags</span>
          {tags.map((tag) => (
            <FilterChip
              key={tag}
              label={tag}
              unavailable={!available.has(tag)}
              onRemove={() => updateTags(tags.filter((item) => item !== tag))}
            />
          ))}
          <Button variant="quiet" type="button" onClick={clearFilters}>
            Clear filters
          </Button>
        </div>
      ) : null}
      <p className="catalog-result-count" aria-live="polite">
        {datasets.length} datasets
      </p>
      {datasets.length === 0 ? (
        catalog.datasets.length === 0 && !query && tags.length === 0 ? (
          <EmptyDatasets />
        ) : (
          <div className="empty-state">
            <h2>No matching datasets</h2>
            <p>Try changing your search or tags.</p>
            <Button variant="quiet" type="button" onClick={clearFilters}>
              Clear filters
            </Button>
          </div>
        )
      ) : (
        <DatasetTable datasets={datasets} />
      )}
    </div>
  );
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  return (
    <div className="page">
      <header className="topbar">
        <h1>Datasets</h1>
      </header>
      <div className="page-body">
        <CatalogAlert error={error} />
      </div>
    </div>
  );
}

function DatasetTable({ datasets }: { datasets: Dataset[] }) {
  return (
    <div className="table-wrap">
      <div className="dataset-cards">
        {datasets.map((dataset) => (
          <article className="dataset-card" key={dataset.id}>
            <div className="dataset-card-heading">
              <Link className="row-link" to={`/datasets/${encodeURIComponent(dataset.id)}`}>
                {dataset.name}
              </Link>
              <DatasetMenu dataset={dataset} />
            </div>
            <p>{dataset.repo_id ?? dataset.source_type}</p>
            <p className="cell-sub mono">{sourceDetail(dataset)}</p>
            <p>{formatCount(dataset.rows_kept)} rows kept</p>
            <p>{dataset.tags.slice(0, 2).join(", ") || "No tags"}</p>
            <details>
              <summary>Details</summary>
              <p>
                Retention: <Retention dataset={dataset} />
              </p>
              <p>Segments: {dataset.segment_keys.join(", ") || "None"}</p>
              <p>Tags: {dataset.tags.join(", ") || "None"}</p>
              <p>Created: {formatDate(dataset.created_at)}</p>
              <p>Processor: {dataset.processor_id}</p>
            </details>
          </article>
        ))}
      </div>
      <table className="dataset-table catalog-table">
        <caption className="sr-only">Datasets</caption>
        <colgroup>
          <col style={{ width: "28%" }} />
          <col style={{ width: "20%" }} />
          <col style={{ width: "10%" }} />
          <col style={{ width: "12%" }} />
          <col style={{ width: "12%" }} />
          <col />
          <col style={{ width: "56px" }} />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Source</th>
            <th className="num" scope="col">
              Rows kept
            </th>
            <th scope="col">Retention</th>
            <th scope="col">Segments</th>
            <th scope="col">Tags</th>
            <th scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {datasets.map((dataset) => (
            <tr key={dataset.id}>
              <th scope="row">
                <Link className="row-link" to={`/datasets/${encodeURIComponent(dataset.id)}`}>
                  {dataset.name}
                </Link>
              </th>
              <td>
                <span className="cell-main">{dataset.repo_id ?? dataset.source_type}</span>
                <span className="cell-sub mono">{sourceDetail(dataset)}</span>
              </td>
              <td className="num">{formatCount(dataset.rows_kept)}</td>
              <td>
                <Retention dataset={dataset} />
              </td>
              <td>
                <Values values={dataset.segment_keys} />
              </td>
              <td>
                <Values values={dataset.tags} />
              </td>
              <td className="dataset-actions">
                <DatasetMenu dataset={dataset} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Values({ values }: { values: string[] }) {
  if (!values.length) return <span>—</span>;
  return (
    <span>
      {values.slice(0, 2).join(", ")}
      {values.length > 2 && (
        <details>
          <summary>+{values.length - 2}</summary>
          {values.join(", ")}
        </details>
      )}
    </span>
  );
}

function Retention({ dataset }: { dataset: Dataset }) {
  const share = dataset.rows_loaded === 0 ? 0 : dataset.rows_kept / dataset.rows_loaded;
  const percent = Math.round(share * 100);
  return (
    <span className="retention" title={`${dataset.rows_kept} of ${dataset.rows_loaded} loaded rows kept`}>
      <span aria-hidden="true" className="retention-bar">
        <span style={{ width: `${percent}%` }} />
      </span>
      <span className="mono">{percent}%</span>
    </span>
  );
}

function EmptyDatasets() {
  return (
    <div className="empty-state">
      <Database aria-hidden="true" size={20} />
      <h2>No datasets yet</h2>
      <p>Import a dataset from Hugging Face or register one from Python.</p>
      <Link className="button-ghost" to="/dataset-imports/new">
        <Plus aria-hidden="true" size={16} />
        Add dataset
      </Link>
    </div>
  );
}

function sourceDetail(dataset: Dataset): string {
  const parts = [
    dataset.split === null ? null : `${dataset.split} split`,
    dataset.config === null ? null : `${dataset.config} config`,
    dataset.revision === null ? null : `@${dataset.revision}`,
  ].filter((part): part is string => part !== null && part !== "");
  return parts.length === 0 ? dataset.source_type : parts.join(" · ");
}
