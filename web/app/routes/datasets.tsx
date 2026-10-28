import { Database, Plus, X } from "lucide-react";
import { Link, useRouteLoaderData } from "react-router";

import { CatalogError, createTags, flattenTags, tagForest, type Dataset } from "../catalog";
import { CatalogAlert, type TagActionData } from "../shell";
import type { clientLoader as rootLoader } from "../root";
import { datasetsUnder } from "../shared/catalog-view";
import { formatCount, formatDate } from "../shared/format";
import type { Route } from "./+types/datasets";

export function meta() {
  return [{ title: "Datasets · Evaluation hub" }];
}

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  const tag = new URL(request.url).searchParams.get("tag");
  return { tag };
}

export async function clientAction({ request }: Route.ClientActionArgs): Promise<TagActionData> {
  const form = await request.formData();
  const name = String(form.get("name") ?? "").trim();
  const parent = String(form.get("parent") ?? "").trim();
  if (name === "" || name.includes("/")) {
    return { error: "A tag name cannot be empty or contain /." };
  }
  try {
    await createTags(tagForest(parent, name));
  } catch (error) {
    if (error instanceof CatalogError) return { error: error.message };
    throw error;
  }
  return { created: true };
}

export default function Datasets({ loaderData }: Route.ComponentProps) {
  const { tag } = loaderData;
  const catalog = useRouteLoaderData<typeof rootLoader>("root");
  if (catalog === undefined) throw new CatalogError("The catalog could not be loaded.", 500);
  if (tag && !flattenTags(catalog.tags).some((node) => node.path === tag)) {
    return <CatalogAlert error={new CatalogError(`Unknown tag: ${tag}`, 404)} />;
  }
  const datasets = datasetsUnder(catalog.datasets, tag);
  return (
    <div className="page">
      <header className="topbar">
        <div className="title-row">
          <h1>Datasets</h1>
          <span className="title-count mono">{datasets.length}</span>
          {tag === null ? null : (
            <span className="filter-token">
              <span className="mono">{tag}</span>
              <Link aria-label="Clear tag filter" className="token-clear" to="/datasets">
                <X aria-hidden="true" size={12} strokeWidth={2} />
              </Link>
            </span>
          )}
        </div>
        <div className="topbar-actions">
          <Link className="button-ghost button-small" to="/dataset-imports">
            Import jobs
          </Link>
          <Link className="button-ghost button-small" to="/dataset-imports/new">
            <Plus aria-hidden="true" size={13} />
            Add dataset
          </Link>
        </div>
      </header>
      {datasets.length === 0 ? <EmptyDatasets tag={tag} /> : <DatasetTable datasets={datasets} />}
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
      <table className="dataset-table">
        <caption className="sr-only">Datasets</caption>
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
            <th className="num" scope="col">
              Created
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
                <span className="cell-sub mono">{dataset.processor_id}</span>
              </th>
              <td>
                <span className="cell-main">{dataset.repo_id ?? dataset.source_type}</span>
                <span className="cell-sub mono">{sourceDetail(dataset)}</span>
              </td>
              <td className="num">{formatCount(dataset.rows_kept)}</td>
              <td>
                <Retention dataset={dataset} />
              </td>
              <td className="muted">{dataset.segment_keys.length === 0 ? "—" : dataset.segment_keys.join(", ")}</td>
              <td className="muted tags-cell" title={dataset.tags.join(", ")}>
                {dataset.tags.length === 0 ? "—" : dataset.tags.map((tag) => tag.split("/").at(-1)).join(", ")}
              </td>
              <td className="num muted">{formatDate(dataset.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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

function EmptyDatasets({ tag }: { tag: string | null }) {
  if (tag === null) {
    return (
      <div className="empty-state">
        <Database aria-hidden="true" size={20} strokeWidth={1.5} />
        <h2>No datasets yet</h2>
        <p>Import a dataset from Hugging Face or register one from Python.</p>
        <Link className="button-ghost" to="/dataset-imports/new">
          <Plus aria-hidden="true" size={13} />
          Add dataset
        </Link>
        <Link className="button-ghost" to="/dataset-imports">
          View import jobs
        </Link>
        <pre className="mono">{`repo.register("name", source, processor, processor_id="...")`}</pre>
      </div>
    );
  }
  return (
    <div className="empty-state">
      <Database aria-hidden="true" size={20} strokeWidth={1.5} />
      <h2>No datasets under this tag</h2>
      <p>
        Datasets tagged <span className="mono">{tag}</span> or any tag inside it appear here.
      </p>
      <Link className="button-ghost" to="/datasets">
        Show all datasets
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
