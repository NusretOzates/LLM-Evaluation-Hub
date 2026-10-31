import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useRouteLoaderData } from "react-router";
import { flattenTags } from "../../catalog";
import type { JsonValue } from "../../catalog-types";
import type { clientLoader as rootLoader } from "../../root";
import { Button, StatusLabel } from "../../shared/controls";
import {
  api,
  defaultGeneration,
  defaultOutput,
  type Generation,
  type Output,
  type Profile,
  type Result,
  type Run,
  type RunSpec,
} from "./api";
import { message } from "./connections";
import { OutputEditor } from "./output-editor";

export function Runs() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .runs()
        .then((v) => {
          if (alive) setRuns(v);
        })
        .catch((e) => {
          if (alive) setError(message(e));
        });
    void load();
    const timer = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  return (
    <div className="page">
      <header className="topbar">
        <h1>Inference runs</h1>
        <Link className="control-button control-button-primary" to="/inference/new">
          New run
        </Link>
      </header>
      <div className="page-body inference-page">
        {error && (
          <p role="alert" className="field-error">
            {error}
          </p>
        )}
        {runs.length === 0 ? (
          <p>No inference runs yet.</p>
        ) : (
          <div className="inference-list">
            {runs.map((run) => (
              <Link className="inference-card" key={run.id} to={`/inference/runs/${run.id}`}>
                <div>
                  <h2>{run.datasets.map((d) => d.name).join(", ") || "Inference run"}</h2>
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
export function NewRun() {
  const catalog = useRouteLoaderData<typeof rootLoader>("root");
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState("{}");
  const [preview, setPreview] = useState<JsonValue>(null);
  const [test, setTest] = useState<JsonValue>(null);
  const [ordinal, setOrdinal] = useState(0);
  const [exampleDataset, setExampleDataset] = useState("");
  const [defaults, setDefaults] = useState<Record<string, Output>>({});
  const [invalidOutputs, setInvalidOutputs] = useState<string[]>([]);
  const [spec, setSpec] = useState<RunSpec>({
    dataset_ids: [],
    tags: [],
    profile_id: "",
    generation: defaultGeneration,
    output_overrides: {},
    concurrency: 4,
    rpm: 60,
    timeout_seconds: 120,
    retries: 2,
  });
  useEffect(() => {
    Promise.all([api.profiles(), api.runs()])
      .then(([p, r]) => {
        setProfiles(p);
        setRuns(r);
      })
      .catch((e) => setError(message(e)));
  }, []);
  useEffect(() => {
    let alive = true;
    const timer = setInterval(() => {
      void api
        .runs()
        .then((value) => {
          if (alive) setRuns(value);
        })
        .catch(() => {
          /* The initial load reports API errors. */
        });
    }, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  if (!catalog) return <p>Catalog unavailable.</p>;
  const selected = catalog.datasets.filter(
    (d) =>
      spec.dataset_ids.includes(d.id) ||
      spec.tags.some((tag) => d.tags.some((path) => path === tag || path.startsWith(`${tag}/`))),
  );
  const profile = profiles.find((p) => p.id === spec.profile_id);
  const testId = exampleDataset || selected[0]?.id || "";
  const active = runs.some((r) => r.state === "running");
  function generation(change: Partial<Generation>) {
    setSpec({ ...spec, generation: { ...spec.generation, ...change } });
  }
  async function configure() {
    try {
      const pairs = await Promise.all(selected.map(async (d) => [d.id, await api.output(d.id)] as const));
      setDefaults(Object.fromEntries(pairs));
      setStep(1);
      setError("");
    } catch (e) {
      setError(message(e));
    }
  }
  function parseAdvanced() {
    const parsed: unknown = JSON.parse(advanced);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
      throw new Error("Advanced parameters must be a JSON object.");
    return parsed as Record<string, JsonValue>;
  }
  function effectiveSpec(): RunSpec {
    return { ...spec, generation: { ...spec.generation, advanced: parseAdvanced() } };
  }
  async function showExample(testRequest: boolean) {
    setError("");
    try {
      const s = effectiveSpec();
      const body = {
        profile_id: s.profile_id,
        dataset_id: testId,
        ordinal,
        generation: s.generation,
        timeout_seconds: s.timeout_seconds,
        retries: s.retries,
        rpm: s.rpm,
        output: s.output_overrides[testId] ?? defaults[testId] ?? defaultOutput,
      };
      if (testRequest) setTest(await api.test(body));
      else setPreview(await api.preview(body));
    } catch (e) {
      setError(message(e));
    }
  }
  async function create() {
    setBusy(true);
    setError("");
    try {
      const run = await api.create(effectiveSpec());
      navigate(`/inference/runs/${run.id}`);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <header className="topbar">
        <Link to="/inference">Inference runs</Link>
        <h1>New run</h1>
      </header>
      <div className="page-body inference-page">
        <nav aria-label="Run setup steps" className="inference-steps">
          <span aria-current={step === 0 ? "step" : undefined}>1. Datasets</span>
          <span aria-current={step === 1 ? "step" : undefined}>2. Configuration</span>
          <span aria-current={step === 2 ? "step" : undefined}>3. Review</span>
        </nav>
        {error && (
          <p role="alert" className="field-error">
            {error}
          </p>
        )}
        {step === 0 && (
          <>
            <div className="inference-panel">
              <h2>Choose datasets</h2>
              <p className="muted">Select datasets directly or include all datasets with a tag.</p>
              {catalog.datasets.map((d) => (
                <label className="check" key={d.id}>
                  <input
                    type="checkbox"
                    checked={spec.dataset_ids.includes(d.id)}
                    onChange={(e) =>
                      setSpec({
                        ...spec,
                        dataset_ids: e.target.checked
                          ? [...spec.dataset_ids, d.id]
                          : spec.dataset_ids.filter((id) => id !== d.id),
                      })
                    }
                  />
                  {d.name}
                </label>
              ))}
              <h2>Tags</h2>
              {flattenTags(catalog.tags).map((tag) => (
                <label className="check" key={tag.path}>
                  <input
                    type="checkbox"
                    checked={spec.tags.includes(tag.path)}
                    onChange={(e) =>
                      setSpec({
                        ...spec,
                        tags: e.target.checked ? [...spec.tags, tag.path] : spec.tags.filter((x) => x !== tag.path),
                      })
                    }
                  />
                  {tag.path}
                </label>
              ))}
              <p>{selected.length} datasets selected</p>
            </div>
            <Button variant="primary" disabled={!selected.length} onClick={() => void configure()}>
              Continue
            </Button>
          </>
        )}
        {step === 1 && (
          <>
            <div className="inference-panel">
              <h2>Connection and generation</h2>
              <label>
                Connection
                <select
                  value={spec.profile_id}
                  onChange={(e) =>
                    setSpec({
                      ...spec,
                      profile_id: e.target.value,
                      generation: { ...spec.generation, effort: null, thinking: null },
                    })
                  }
                >
                  <option value="">Choose a connection</option>
                  {profiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {p.model}
                    </option>
                  ))}
                </select>
              </label>
              {!profiles.length && (
                <p>
                  <Link to="/connections">Create a connection</Link> first.
                </p>
              )}
              <div className="inference-grid">
                {(
                  [
                    ["max_tokens", "Maximum generated tokens"],
                    ["temperature", "Temperature"],
                    ["top_p", "Top-p"],
                    ["seed", "Seed"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      type="number"
                      step={key === "temperature" || key === "top_p" ? "any" : "1"}
                      value={spec.generation[key] ?? ""}
                      onChange={(e) => generation({ [key]: e.target.value === "" ? null : Number(e.target.value) })}
                      placeholder="Server default"
                    />
                  </label>
                ))}
                {profile?.reasoning_mode === "effort" && (
                  <label>
                    Effort
                    <select
                      value={spec.generation.effort ?? ""}
                      onChange={(e) => generation({ effort: e.target.value || null })}
                    >
                      <option value="">Server default</option>
                      {profile.effort_levels.map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                  </label>
                )}
                {profile?.reasoning_mode === "thinking" && (
                  <label>
                    Thinking
                    <select
                      value={spec.generation.thinking === null ? "" : String(spec.generation.thinking)}
                      onChange={(e) =>
                        generation({ thinking: e.target.value === "" ? null : e.target.value === "true" })
                      }
                    >
                      <option value="">Server default</option>
                      <option value="true">On</option>
                      <option value="false">Off</option>
                    </select>
                  </label>
                )}
              </div>
              <label>
                Advanced request parameters (JSON object)
                <textarea className="inference-json" value={advanced} onChange={(e) => setAdvanced(e.target.value)} />
              </label>
              <p className="hint">Protected fields and conflicts with common controls are rejected.</p>
            </div>
            <div className="inference-panel">
              <h2>Execution limits</h2>
              <div className="inference-grid">
                {(
                  [
                    ["concurrency", "Concurrent requests"],
                    ["rpm", "Requests per minute"],
                    ["timeout_seconds", "Timeout (seconds)"],
                    ["retries", "Retries"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      type="number"
                      min={key === "retries" ? 0 : 1}
                      value={spec[key]}
                      onChange={(e) => setSpec({ ...spec, [key]: Number(e.target.value) })}
                    />
                  </label>
                ))}
              </div>
            </div>
            <div className="inference-panel">
              <h2>Dataset output</h2>
              {selected.map((d) => (
                <details key={d.id}>
                  <summary>
                    {d.name} · {spec.output_overrides[d.id] ? "Override" : "Dataset default"}
                  </summary>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={!!spec.output_overrides[d.id]}
                      onChange={(e) => {
                        const overrides = { ...spec.output_overrides };
                        if (e.target.checked) overrides[d.id] = defaults[d.id] ?? defaultOutput;
                        else delete overrides[d.id];
                        setSpec({ ...spec, output_overrides: overrides });
                      }}
                    />{" "}
                    Override output format for this run
                  </label>
                  {spec.output_overrides[d.id] && (
                    <OutputEditor
                      onValidityChange={(valid) =>
                        setInvalidOutputs((items) =>
                          valid
                            ? items.includes(d.id)
                              ? items.filter((id) => id !== d.id)
                              : items
                            : items.includes(d.id)
                              ? items
                              : [...items, d.id],
                        )
                      }
                      value={spec.output_overrides[d.id]}
                      onChange={(output) =>
                        setSpec({ ...spec, output_overrides: { ...spec.output_overrides, [d.id]: output } })
                      }
                    />
                  )}
                </details>
              ))}
            </div>
            <div className="inference-actions">
              <Button onClick={() => setStep(0)}>Back</Button>
              <Button
                variant="primary"
                disabled={!spec.profile_id || invalidOutputs.some((id) => !!spec.output_overrides[id])}
                onClick={() => {
                  try {
                    parseAdvanced();
                    setError("");
                    setStep(2);
                  } catch (e) {
                    setError(message(e));
                  }
                }}
              >
                Review
              </Button>
            </div>
          </>
        )}
        {step === 2 && (
          <>
            <div className="inference-panel">
              <h2>Review run</h2>
              <p>
                {selected.length} datasets · {profile?.name} · {spec.concurrency} concurrent · {spec.rpm}{" "}
                requests/minute
              </p>
              <p className="muted">Settings and dataset identities are frozen when the run is created.</p>
              {selected.map((d) => (
                <p key={d.id}>
                  {d.name}: All rows · {(spec.output_overrides[d.id] ?? defaults[d.id])?.kind}
                </p>
              ))}
            </div>
            <div className="inference-panel">
              <h2>Example request</h2>
              <div className="inference-grid">
                <label>
                  Dataset
                  <select value={testId} onChange={(e) => setExampleDataset(e.target.value)}>
                    {selected.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Row ordinal (zero-based)
                  <input type="number" min="0" value={ordinal} onChange={(e) => setOrdinal(Number(e.target.value))} />
                </label>
              </div>
              <div className="inference-actions">
                <Button onClick={() => void showExample(false)}>Preview request</Button>
                <Button disabled={active} onClick={() => void showExample(true)}>
                  Test example
                </Button>
              </div>
              {active && <p className="hint">Tests are unavailable while a run is active.</p>}
              {preview !== null && (
                <>
                  <h3>Effective request</h3>
                  <pre>{JSON.stringify(preview, null, 2)}</pre>
                </>
              )}
              {test !== null && (
                <>
                  <h3>Test response</h3>
                  <pre>{JSON.stringify(test, null, 2)}</pre>
                </>
              )}
            </div>
            <div className="inference-actions">
              <Button onClick={() => setStep(1)}>Back</Button>
              <Button variant="primary" loading={busy} onClick={() => void create()}>
                Create run
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
export function RunDetail() {
  const { id = "" } = useParams();
  const [run, setRun] = useState<Run | null>(null);
  const [results, setResults] = useState<Result[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [input, setInput] = useState<Record<string, JsonValue>>({});
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    void revision;
    let alive = true;
    let pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const [r, rows] = await Promise.all([api.run(id), api.results(id, offset, filter)]);
        if (alive) {
          setRun(r);
          setResults(rows.results);
          setTotalResults(rows.total);
          setError("");
        }
      } catch (e) {
        if (alive) setError(message(e));
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [id, offset, filter, revision]);
  async function action(kind: "cancel" | "resume") {
    try {
      await api.action(id, kind);
      setRevision((value) => value + 1);
    } catch (e) {
      setError(message(e));
    }
  }
  async function loadInput(row: Result) {
    const key = `${row.dataset_id}:${row.ordinal}`;
    try {
      const page = await api.input(id, row.dataset_id, row.ordinal);
      setInput((v) => ({ ...v, [key]: page }));
    } catch {
      setInput((v) => ({ ...v, [key]: "Input unavailable. The source dataset may have been purged." }));
    }
  }
  if (!run) return <div className="page-body">{error || "Loading run…"}</div>;
  return (
    <div className="page">
      <header className="topbar">
        <Link to="/inference">Inference runs</Link>
        <h1>Run detail</h1>
        <StatusLabel status={run.state} />
      </header>
      <div className="page-body inference-page">
        {error && (
          <p role="alert" className="field-error">
            {error}
          </p>
        )}
        <div className="inference-panel">
          <div className="inference-actions">
            <h2>
              {run.completed} / {run.total} rows completed
            </h2>
            {["queued", "running", "interrupted"].includes(run.state) && (
              <Button variant="danger" onClick={() => void action("cancel")}>
                Cancel run
              </Button>
            )}
            {run.state === "interrupted" && <Button onClick={() => void action("resume")}>Resume run</Button>}
          </div>
          {run.error && (
            <p role="alert" className="field-error">
              {run.error}
            </p>
          )}
          <progress max={run.total || 1} value={run.completed} aria-label="Run progress" />
          <p className="muted">Created {new Date(run.created_at).toLocaleString()}</p>
          <div className="inference-grid">
            {run.datasets.map((d) => (
              <div className="inference-card" key={d.id}>
                <div>
                  <strong>{d.name}</strong>
                  <p>
                    {d.completed} / {d.rows} rows · {d.errors} errors
                  </p>
                  {!d.input_available && <p>Source input unavailable</p>}
                </div>
              </div>
            ))}
          </div>
          <details>
            <summary>Frozen settings</summary>
            <pre>{JSON.stringify({ spec: run.spec, datasets: run.datasets }, null, 2)}</pre>
          </details>
        </div>
        <div className="inference-panel">
          <h2>Results</h2>
          <label>
            Filter results
            <select
              value={filter}
              onChange={(e) => {
                setOffset(0);
                setFilter(e.target.value);
              }}
            >
              <option value="all">All results</option>
              <option value="errors">Errors and validation issues</option>
              {run.datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          {results.map((row) => {
            const dataset = run.datasets.find((d) => d.id === row.dataset_id);
            const key = `${row.dataset_id}:${row.ordinal}`;
            return (
              <details className="result-row" key={key}>
                <summary>
                  {dataset?.name ?? row.dataset_id} · Row {row.ordinal + 1} (source {row.source_index}) · {row.status}
                </summary>
                <p>
                  {row.latency_ms === null ? "Timing unavailable" : `${row.latency_ms.toFixed(0)} ms`} · {row.attempts}{" "}
                  attempts · Finish: {row.finish_reason ?? "unavailable"}
                </p>
                {row.error && <p className="field-error">{row.error}</p>}
                {row.validation_errors.map((e) => (
                  <p className="field-error" key={e}>
                    {e}
                  </p>
                ))}
                <h3>Content</h3>
                <pre>{row.content ?? "No content"}</pre>
                <h3>Parsed output</h3>
                <pre>{JSON.stringify(row.parsed, null, 2)}</pre>
                <h3>Tool calls</h3>
                <pre>{JSON.stringify(row.tool_calls, null, 2)}</pre>
                <h3>Usage</h3>
                <pre>{JSON.stringify(row.usage, null, 2)}</pre>
                <details>
                  <summary>Raw response</summary>
                  <pre>{JSON.stringify(row.raw_response, null, 2)}</pre>
                </details>
                {dataset?.input_available ? (
                  <Button onClick={() => void loadInput(row)}>Load source input</Button>
                ) : (
                  <p>Source input unavailable after dataset purge.</p>
                )}
                {key in input && <pre>{JSON.stringify(input[key], null, 2)}</pre>}
              </details>
            );
          })}
          <div className="inference-actions">
            <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>
              Previous
            </Button>
            <span>
              Rows {totalResults ? offset + 1 : 0}–{offset + results.length} of {totalResults}
            </span>
            <Button disabled={offset + results.length >= totalResults} onClick={() => setOffset(offset + 20)}>
              Next
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
