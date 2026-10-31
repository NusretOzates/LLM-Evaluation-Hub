import { Link, useRouteLoaderData, type ShouldRevalidateFunctionArgs } from "react-router";

import { addTags, CatalogError, getDataset, listDatasets, listExamples, removeTags } from "../catalog";

import { CatalogAlert } from "../shared/feedback";

import { DatasetInspector } from "../features/dataset-inspector/inspector";

import { PAGE_SIZE, readPosition } from "../features/dataset-inspector/model";

import type { clientLoader as rootLoader } from "../root";

import type { Route } from "./+types/dataset";

type ActionData = { error: string } | { ok: true };

export function meta() {
  return [{ title: "Dataset · Evaluation hub" }];
}

export async function clientLoader({ params, request }: Route.ClientLoaderArgs) {
  const name = params.name;

  if (name === undefined || name === "") {
    throw new CatalogError("Dataset name is missing.", 404);
  }

  const { offset } = readPosition(new URL(request.url).searchParams);

  const dataset = await resolveDataset(name, request.signal);

  const page = await listExamples(dataset.id, offset, PAGE_SIZE, request.signal);

  return { dataset, page };
}

export function shouldRevalidate({
  currentUrl,

  defaultShouldRevalidate,

  formMethod,

  nextUrl,
}: ShouldRevalidateFunctionArgs) {
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
    if (intent !== "attach" && intent !== "detach") return { error: "Unknown tag action." };

    const dataset = await resolveDataset(name, request.signal);

    if (intent === "detach") await removeTags(dataset.id, [path]);
    else await addTags(dataset.id, [path]);
  } catch (error) {
    if (error instanceof CatalogError) return { error: error.message };

    throw error;
  }

  return { ok: true };
}

export default function DatasetPage({ loaderData }: Route.ComponentProps) {
  const catalog = useRouteLoaderData<typeof rootLoader>("root");

  if (catalog === undefined) throw new CatalogError("The catalog could not be loaded.", 500);

  return (
    <DatasetInspector
      key={loaderData.dataset.id}
      dataset={loaderData.dataset}
      page={loaderData.page}
      tags={catalog.tags}
    />
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

async function resolveDataset(identity: string, signal: AbortSignal) {
  // Preserve existing name bookmarks while new links always use immutable IDs.

  try {
    return await getDataset(identity, signal);
  } catch (error) {
    if (!(error instanceof CatalogError) || error.status !== 404) throw error;

    const dataset = (await listDatasets(null, signal)).find((item) => item.name === identity);

    if (dataset === undefined) throw error;

    return dataset;
  }
}
