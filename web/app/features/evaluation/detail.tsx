import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { Button, StatusLabel } from "../../shared/controls";
import { ConfirmDialog } from "../../shared/dialog";
import { request, post, type Evaluation, type Result, type Summary } from "./api";

export default function EvaluationDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<Evaluation | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<Result[]>([]);
  const [group, setGroup] = useState("overall");
  const [segment, setSegment] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [inspect, setInspect] = useState<{
    input: {
      available: boolean;
      example: unknown;
      response: unknown;
      processed_response: unknown;
      preprocess_error: string | null;
    };
    outcome: Result;
  } | null>(null);
  const [datasetScope, setDatasetScope] = useState("");
  const [tagScope, setTagScope] = useState("");
  const [status, setStatus] = useState("");
  const [rowTotal, setRowTotal] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => {
    const load = async () => {
      try {
        const scope = new URLSearchParams();
        if (datasetScope) scope.append("dataset_ids", datasetScope);
        if (tagScope) scope.append("tag_paths", tagScope);
        const summaryQuery = new URLSearchParams(scope);
        summaryQuery.set("group_by", group);
        summaryQuery.set("segment_key", segment);
        const rowQuery = new URLSearchParams(scope);
        rowQuery.set("offset", String(offset));
        rowQuery.set("limit", "25");
        if (status) rowQuery.set("status", status);
        const [r, s, p] = await Promise.all([
          request<Evaluation>(`/evaluations/${id}`),
          request<Summary>(`/evaluations/${id}/summary?${summaryQuery}`),
          request<{ results: Result[]; total: number }>(`/evaluations/${id}/results?${rowQuery}`),
        ]);
        setRun(r);
        setSummary(s);
        setRows(p.results);
        setRowTotal(p.total);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    void load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [id, group, segment, offset, datasetScope, tagScope, status]);
  const action = async (name: string) => {
    try {
      if (name === "delete") {
        await request(`/evaluations/${id}`, { method: "DELETE" });
        navigate("/evaluations");
      } else await post(`/evaluations/${id}/${name}`, {});
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <div className="page">
      <header className="topbar">
        <h1>{run?.settings.name ?? "Evaluation"}</h1>
        {run && (
          <div className="evaluation-actions">
            <StatusLabel status={run.state} />
            {["completed", "canceled", "interrupted"].includes(run.state) && (
              <Button variant="destructive" onClick={() => setConfirmDelete(true)}>
                Delete
              </Button>
            )}
          </div>
        )}
      </header>
      <ConfirmDialog
        open={confirmDelete}
        title="Delete evaluation?"
        description="Permanently delete this evaluation and its evidence? The source inference and datasets are kept."
        confirmLabel="Delete evaluation"
        destructive
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => action("delete")}
      />
      <div className="page-body inference-page evaluation-report">
        {error && <p role="alert">{error}</p>}
        {run && (
          <>
            <div className="evaluation-progress">
              <strong>
                {run.completed} / {run.total} rows processed
              </strong>
              <progress value={run.completed} max={run.total} />
              <span>{summary?.partial ? "Partial results" : "Evaluation finished"}</span>
            </div>
            <p>
              {["queued", "running", "interrupted"].includes(run.state) && (
                <Button onClick={() => void action("cancel")}>Cancel</Button>
              )}{" "}
              {run.state === "interrupted" && <Button onClick={() => void action("resume")}>Resume</Button>}
            </p>
            <div className="evaluation-scope">
              <label>
                Dataset{" "}
                <select
                  value={datasetScope}
                  onChange={(e) => {
                    setDatasetScope(e.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="">All datasets</option>
                  {run.datasets.map((d) => (
                    <option value={d.dataset_id} key={d.dataset_id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Tag{" "}
                <select
                  value={tagScope}
                  onChange={(e) => {
                    setTagScope(e.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="">All tags</option>
                  {Array.from(
                    new Set(
                      run.datasets.flatMap((d) =>
                        d.tags.flatMap((tag) => tag.split("/").map((_, i, parts) => parts.slice(0, i + 1).join("/"))),
                      ),
                    ),
                  )
                    .sort()
                    .map((tag) => (
                      <option key={tag}>{tag}</option>
                    ))}
                </select>
              </label>
            </div>
            <section>
              <h2>Scores and coverage</h2>
              <label className="group-picker">
                Group by{" "}
                <select value={group} onChange={(e) => setGroup(e.target.value)}>
                  <option value="overall">Overall</option>
                  <option value="dataset">Dataset</option>
                  <option value="segment">Segment</option>
                  <option value="tag">Tag</option>
                </select>
              </label>{" "}
              {group === "segment" && (
                <label>
                  Segment key <input value={segment} onChange={(e) => setSegment(e.target.value)} />
                </label>
              )}
              <div className="evaluation-table">
                <table>
                  <thead>
                    <tr>
                      <th>Group</th>
                      <th>Mean</th>
                      <th>Scored / selected</th>
                      <th>Pending</th>
                      <th>Failed</th>
                      <th>Ineligible</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary?.groups.map((g, i) => (
                      <tr key={g.name ?? `missing-${i}`}>
                        <td>{g.name ?? "Not specified"}</td>
                        <td>
                          {Object.entries(g.means)
                            .map(([k, v]) => `${k}: ${v === null ? "No valid scores" : v.toFixed(3)}`)
                            .join(" · ")}
                        </td>
                        <td>
                          {g.scored} / {g.selected} ({(g.coverage * 100).toFixed(0)}%)
                        </td>
                        <td>{g.pending}</td>
                        <td>{g.failed}</td>
                        <td>{g.source_ineligible}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section>
              <h2>Rows</h2>
              <label className="group-picker">
                Status (rows only){" "}
                <select
                  value={status}
                  onChange={(e) => {
                    setStatus(e.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="">All statuses</option>
                  <option value="scored">Scored</option>
                  <option value="pending">Pending</option>
                  <option value="failed">Failed</option>
                  <option value="source_ineligible">Source ineligible</option>
                </select>
              </label>
              <p className="hint">Status filters rows only; scores and coverage use the dataset and tag scope above.</p>
              <div className="evaluation-table">
                <table>
                  <thead>
                    <tr>
                      <th>Dataset</th>
                      <th>Row</th>
                      <th>Status</th>
                      <th>Scores</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={`${row.dataset_id}-${row.ordinal}`}>
                        <td>{run.datasets.find((d) => d.dataset_id === row.dataset_id)?.name}</td>
                        <td>{row.ordinal + 1}</td>
                        <td>{row.status ?? "pending"}</td>
                        <td>
                          {row.scores
                            ? Object.entries(row.scores)
                                .map(([name, value]) => `${name} ${value.toFixed(3)}`)
                                .join(" · ")
                            : "—"}
                        </td>
                        <td>
                          <Button
                            onClick={() =>
                              void request<{
                                available: boolean;
                                example: unknown;
                                response: unknown;
                                processed_response: unknown;
                                preprocess_error: string | null;
                              }>(`/evaluations/${id}/inputs/${row.dataset_id}/${row.ordinal}`)
                                .then((input) => setInspect({ input, outcome: row }))
                                .catch((e: Error) => setError(e.message))
                            }
                          >
                            Inspect
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p>
                <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>
                  Previous
                </Button>{" "}
                <Button disabled={offset + 25 >= rowTotal} onClick={() => setOffset(offset + 25)}>
                  Next
                </Button>
              </p>
            </section>
            {inspect !== null && (
              <details open>
                <summary>Row evidence</summary>
                {!inspect.input.available && (
                  <p>Original input is unavailable. Retained evaluation evidence remains below.</p>
                )}
                <h3>Processed candidate</h3>
                {inspect.input.preprocess_error ? (
                  <p>{inspect.input.preprocess_error}</p>
                ) : (
                  <pre>{JSON.stringify(inspect.input.processed_response, null, 2)}</pre>
                )}
                <details>
                  <summary>Original input and response</summary>
                  <pre>
                    {JSON.stringify({ example: inspect.input.example, response: inspect.input.response }, null, 2)}
                  </pre>
                </details>
                <details>
                  <summary>Method result and evidence</summary>
                  <pre>{JSON.stringify(inspect.outcome, null, 2)}</pre>
                </details>
              </details>
            )}
            <details>
              <summary>Frozen settings</summary>
              <pre>{JSON.stringify(run.settings, null, 2)}</pre>
            </details>
          </>
        )}
      </div>
    </div>
  );
}
