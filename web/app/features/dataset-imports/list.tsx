import { Clock3 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { CatalogAlert } from "../../shell";
import type { ImportJob } from "./contracts";
import { listImports } from "./transport";
import type { Route } from "./+types/list";

export function meta() {
  return [{ title: "Dataset imports · Evaluation hub" }];
}
export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  return { jobs: await listImports(request.signal) };
}
export default function ImportList({ loaderData }: Route.ComponentProps) {
  const [jobs, setJobs] = useState(loaderData.jobs);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const next = await listImports();
        if (active) {
          setJobs(next);
          setError(null);
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not refresh imports.");
      }
      if (active) timer = setTimeout(() => void refresh(), 4000);
    };
    timer = setTimeout(() => void refresh(), 1000);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);
  return (
    <div className="page">
      <header className="topbar">
        <div className="title-row">
          <h1>Dataset imports</h1>
          <span className="title-count mono">{jobs.length}</span>
        </div>
        <Link className="button-ghost button-small" to="/dataset-imports/new">
          Add dataset
        </Link>
      </header>
      <div className="page-body import-jobs">
        {error ? (
          <p className="alert" role="alert">
            {error}
          </p>
        ) : null}
        {jobs.length === 0 ? (
          <div className="empty-state">
            <Clock3 size={20} />
            <h2>No import jobs</h2>
            <p>Submitted dataset imports will appear here.</p>
            <Link className="button-ghost" to="/dataset-imports/new">
              Add dataset
            </Link>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="dataset-table">
              <caption className="sr-only">Dataset import jobs</caption>
              <thead>
                <tr>
                  <th scope="col">Dataset</th>
                  <th scope="col">State</th>
                  <th scope="col">Progress</th>
                  <th scope="col">Updated</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <JobTableRow job={job} key={job.id} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
function JobTableRow({ job }: { job: ImportJob }) {
  return (
    <tr>
      <th scope="row">
        <Link className="row-link" to={`/dataset-imports/${job.id}`}>
          {job.name}
        </Link>
        <span className="cell-sub mono">{job.id}</span>
      </th>
      <td>
        <span className="job-state" data-state={job.state}>
          {job.state}
        </span>
        <span className="cell-sub">{job.phase}</span>
      </td>
      <td className="mono">
        {job.rows_loaded} loaded · {job.rows_kept} kept · {job.rows_dropped} skipped
      </td>
      <td className="num muted">{new Date(job.updated_at).toLocaleString()}</td>
    </tr>
  );
}
export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  return (
    <div className="page">
      <header className="topbar">
        <h1>Dataset imports</h1>
      </header>
      <div className="page-body">
        <CatalogAlert error={error} />
      </div>
    </div>
  );
}
