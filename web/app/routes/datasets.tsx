import { Database, X } from "lucide-react";
import { Link } from "react-router";

import { CatalogError, createTags, listDatasets, tagForest, type Dataset } from "../catalog";
import { CatalogAlert, type TagActionData } from "../shell";
import type { Route } from "./+types/datasets";

export function meta() {
  return [{ title: "Datasets · Evaluation hub" }];
}

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  const tag = new URL(request.url).searchParams.get("tag");
  return { tag, datasets: await listDatasets(tag) };
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
  const { tag, datasets } = loaderData;
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
                <Link className="row-link" to={`/datasets/${encodeURIComponent(dataset.name)}`}>
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
        <p>Datasets are registered from Python. Each one appears here with its row counts and tags.</p>
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

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en").format(value);
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().slice(0, 10);
}
