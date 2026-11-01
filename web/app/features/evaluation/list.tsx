import { useEffect, useState } from "react";
import { Link } from "react-router";
import { StatusLabel } from "../../shared/controls";
import { request, type Evaluation } from "./api";

export default function Evaluations() {
  const [runs, setRuns] = useState<Evaluation[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const load = () =>
      request<Evaluation[]>("/evaluations")
        .then(setRuns)
        .catch((e: Error) => setError(e.message));
    void load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="page">
      <header className="topbar">
        <h1>Evaluations</h1>
        <Link className="control-button control-button-primary" to="/evaluations/new">
          New evaluation
        </Link>
      </header>
      <div className="page-body inference-page">
        {error && <p role="alert">{error}</p>}
        {runs.length === 0 ? (
          <p>No evaluations yet.</p>
        ) : (
          <div className="inference-list">
            {runs.map((run) => (
              <Link className="inference-card" key={run.id} to={`/evaluations/${run.id}`}>
                <div>
                  <h2>{run.settings.name}</h2>
                  <p className="muted">
                    {new Date(run.created_at).toLocaleString()} · {run.completed} / {run.total} rows
                  </p>
                </div>
                <StatusLabel status={run.state} />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
