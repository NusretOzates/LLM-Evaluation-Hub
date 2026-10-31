import { useEffect, useState } from "react";
import { Link, useNavigate, useRevalidator, useRouteLoaderData } from "react-router";
import { Dialog } from "../../shared/dialog";
import { StatusLabel, Button } from "../../shared/controls";
import { CatalogAlert } from "../../shared/feedback";
import type { clientLoader as rootLoader } from "../../root";
import type { ImportJob } from "./contracts";
import { cancelImport, getImport } from "./transport";
import type { Route } from "./+types/detail";

export function meta() {
  return [{ title: "Import job · Dataset imports" }];
}
export async function clientLoader({ params, request }: Route.ClientLoaderArgs) {
  if (!params.id) throw new Error("Import id is missing.");
  return { job: await getImport(params.id, request.signal) };
}
export default function ImportDetail({ loaderData }: Route.ComponentProps) {
  const [job, setJob] = useState(loaderData.job);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [catalogCheckedFor, setCatalogCheckedFor] = useState<string | null>(null);
  const navigate = useNavigate();
  const { revalidate } = useRevalidator();
  useEffect(() => {
    if (job.state !== "succeeded") return;
    let active = true;
    void revalidate().then(() => {
      if (active) setCatalogCheckedFor(job.id);
    });
    return () => {
      active = false;
    };
  }, [job.id, job.state, revalidate]);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const next = await getImport(job.id);
        if (!active) return;
        setJob(next);
        setError(null);
        if (isActive(next.state)) timer = setTimeout(() => void refresh(), 1200);
      } catch (cause) {
        if (active) {
          setError(cause instanceof Error ? cause.message : "Could not refresh job state.");
          timer = setTimeout(() => void refresh(), 3000);
        }
      }
    };
    if (isActive(job.state)) timer = setTimeout(() => void refresh(), 900);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [job.id, job.state]);
  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      setJob(await cancelImport(job.id));
      setConfirmCancel(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Cancellation could not be confirmed.");
    } finally {
      setBusy(false);
    }
  }
  const retryable = ["failed", "cancelled", "interrupted"].includes(job.state);
  const catalog = useRouteLoaderData<typeof rootLoader>("root");
  const datasetId =
    job.dataset_id && catalog?.datasets.some((dataset) => dataset.id === job.dataset_id) ? job.dataset_id : null;
  return (
    <div className="page">
      <header className="topbar import-topbar">
        <nav aria-label="Breadcrumb" className="crumbs">
          <Link to="/dataset-imports">Dataset imports</Link>
          <span aria-hidden="true">/</span>
          <h1>{job.name}</h1>
        </nav>
        <span className="job-state" data-state={job.state}>
          <StatusLabel status={job.state} />
        </span>
      </header>
      <div className="page-body import-job-detail">
        {error ? (
          <p className="alert" role="alert">
            {error}
          </p>
        ) : null}
        <section className="import-card">
          <header>
            <h2>Import {job.name}</h2>
            <p>{job.phase}</p>
          </header>
          <dl className="job-progress">
            <dt>State</dt>
            <dd>
              <StatusLabel status={job.state} />
            </dd>
            <dt>Rows loaded</dt>
            <dd>{job.rows_loaded}</dd>
            <dt>Rows kept</dt>
            <dd>{job.rows_kept}</dd>
            <dt>Rows skipped</dt>
            <dd>{job.rows_dropped}</dd>
            <dt>Source</dt>
            <dd>
              {job.spec.source.repo_id} · {job.spec.source.split} ·{" "}
              <code className="mono">{job.spec.resolved_sha}</code>
            </dd>
            <dt>Started</dt>
            <dd>{new Date(job.created_at).toLocaleString()}</dd>
          </dl>
          {job.error ? (
            <div className="alert job-error" role="alert">
              <strong>{job.error.category}</strong>
              <p>{job.error.message}</p>
              {job.error.source_index === null ? null : (
                <small>
                  Source row {job.error.source_index + 1}
                  {job.error.line ? ` · line ${job.error.line}` : ""}
                </small>
              )}
            </div>
          ) : null}
          <div className="job-actions">
            {isActive(job.state) ? (
              <button
                className="button-ghost"
                disabled={busy || job.state === "cancelling"}
                onClick={() => setConfirmCancel(true)}
                type="button"
              >
                {job.state === "cancelling" ? "Cancellation requested" : "Cancel import"}
              </button>
            ) : null}
            {retryable ? (
              <Link className="button-ghost" to={`/dataset-imports/new?retry=${encodeURIComponent(job.id)}`}>
                Retry with this specification
              </Link>
            ) : null}
            {job.state === "succeeded" && catalogCheckedFor === job.id && !datasetId ? (
              <p>This dataset is in Trash or has been permanently deleted.</p>
            ) : null}
            {job.state === "succeeded" && datasetId ? (
              <button
                className="button-ghost"
                onClick={() => navigate(`/datasets/${encodeURIComponent(datasetId)}`)}
                type="button"
              >
                Open dataset
              </button>
            ) : null}
          </div>
        </section>
        <details className="import-card">
          <summary>Import specification</summary>
          <dl className="job-progress">
            <dt>Repository</dt>
            <dd>{job.spec.source.repo_id}</dd>
            <dt>Config / split</dt>
            <dd>
              {job.spec.source.config ?? "default"} / {job.spec.source.split}
            </dd>
            <dt>Requested revision</dt>
            <dd>{job.spec.source.revision}</dd>
            <dt>Segments</dt>
            <dd>{job.spec.segment_keys.join(", ") || "None"}</dd>
            <dt>Tags</dt>
            <dd>{job.spec.tags.join(", ") || "None"}</dd>
            <dt>Processor hash</dt>
            <dd>
              <code className="mono">{job.spec.source_hash}</code>
            </dd>
          </dl>
          <details>
            <summary>Processor source</summary>
            <pre className="raw mono">{job.spec.source_code}</pre>
          </details>
        </details>
      </div>
      <Dialog
        open={confirmCancel}
        title="Cancel this import?"
        description="The job will not publish a partial dataset."
        pending={busy}
        onClose={() => setConfirmCancel(false)}
      >
        {error && <p role="alert">{error}</p>}
        <Button autoFocus type="button" disabled={busy} onClick={() => setConfirmCancel(false)}>
          Keep import
        </Button>
        <Button type="button" loading={busy} onClick={() => void cancel()}>
          Request cancellation
        </Button>
      </Dialog>
    </div>
  );
}
function isActive(state: ImportJob["state"]) {
  return state === "queued" || state === "running" || state === "cancelling";
}
export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  return (
    <div className="page">
      <header className="topbar">
        <h1>Import job</h1>
      </header>
      <div className="page-body">
        <CatalogAlert error={error} />
      </div>
    </div>
  );
}
