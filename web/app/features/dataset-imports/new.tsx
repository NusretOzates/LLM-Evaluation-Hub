import { ArrowLeft, ArrowRight, Check, LoaderCircle, RotateCcw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useRouteLoaderData } from "react-router";
import { CatalogError, listDatasets } from "../../catalog";
import type { clientLoader as rootLoader } from "../../root";
import { AvailableTools } from "../../shared/available-tools";
import { TagPicker, toggleTagPath } from "../../shared/tag-picker";
import { CatalogAlert } from "../../shared/feedback";
import { Button } from "../../shared/controls";
import { Dialog } from "../../shared/dialog";
import type { DatasetPreview, ImportLimits, SourceCoordinates, SourceSample } from "./contracts";
import { ProcessorEditor } from "./processor-editor";
import { getImport, getImportSources, loadSourceSample, runDatasetPreview, submitImport } from "./transport";
import type { Route } from "./+types/new";

const STEPS = ["Details", "Source", "Processor", "Review"] as const;
const RESERVED_SEGMENT_KEYS = ["source_index", "conversation", "tools", "expected_output", "extras"];
const TEMPLATE = `def process(row: dict) -> dict | None:\n    # Return None to intentionally skip a source row.\n    return {\n        "conversation": [\n            {"role": "user", "content": row["text"]}\n        ],\n        "tools": [],\n        "expected_output": row.get("label"),\n        "segments": {},\n    }\n`;

type Draft = {
  name: string;
  tags: string[];
  source: SourceCoordinates;
  row_limit: number;
  segment_keys: string[];
  code: string;
};
const initialDraft: Draft = {
  name: "",
  tags: [],
  source: { kind: "hf_dataset", repo_id: "", config: null, split: "train", revision: "main" },
  row_limit: 10000,
  segment_keys: [],
  code: TEMPLATE,
};

export function meta() {
  return [{ title: "Add dataset · Evaluation hub" }];
}
export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  const retry = new URL(request.url).searchParams.get("retry");
  const [sources, retryJob] = await Promise.all([
    getImportSources(request.signal),
    retry === null ? Promise.resolve(null) : getImport(retry, request.signal),
  ]);
  return { retryJob, sources };
}
export default function NewDatasetImport({ loaderData }: Route.ComponentProps) {
  const catalog = useRouteLoaderData<typeof rootLoader>("root");
  const navigate = useNavigate();

  const [step, setStep] = useState(0);
  const importBody = useRef<HTMLDivElement>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: Each step starts at the top of its own content.
  useEffect(() => {
    importBody.current?.scrollTo({ top: 0 });
  }, [step]);
  const [furthestStep, setFurthestStep] = useState(0);
  const [processorTab, setProcessorTab] = useState<"input" | "processor" | "preview">("processor");
  const [draft, setDraft] = useState<Draft>(initialDraft);
  const [codeEdited, setCodeEdited] = useState(false);
  const [replacement, setReplacement] = useState<
    { kind: "columns"; columns: string[] } | { kind: "template"; mode: "none" | "source" | "json" } | null
  >(null);
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [sample, setSample] = useState<SourceSample | null>(null);
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [selectedRow, setSelectedRow] = useState(0);

  const [loadingSample, setLoadingSample] = useState(false);
  const [runningPreview, setRunningPreview] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [checkingName, setCheckingName] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const sampleRequest = useRef(0);
  const previewRequest = useRef(0);
  const nameCheck = useRef<AbortController | null>(null);
  const sampleAbort = useRef<AbortController | null>(null);
  const previewAbort = useRef<AbortController | null>(null);
  const idempotencyKey = useRef<string | null>(null);
  const idempotencyPayload = useRef<string | null>(null);
  useEffect(
    () => () => {
      sampleRequest.current += 1;
      previewRequest.current += 1;
      nameCheck.current?.abort();
      sampleAbort.current?.abort();
      previewAbort.current?.abort();
    },
    [],
  );

  useEffect(() => {
    const retry = loaderData.retryJob;
    if (retry === null) return;
    nameCheck.current?.abort();
    nameCheck.current = null;
    setCheckingName(false);
    sampleRequest.current += 1;
    previewRequest.current += 1;
    sampleAbort.current?.abort();
    previewAbort.current?.abort();
    setLoadingSample(false);
    setRunningPreview(false);
    setDraft({
      name: retry.name,
      tags: [...retry.spec.tags],
      source: { ...retry.spec.source },
      row_limit: retry.spec.row_limit,
      segment_keys: [...retry.spec.segment_keys],
      code: retry.spec.source_code,
    });
    setSample(null);
    setPreview(null);
    setCodeEdited(true);
    setSelectedColumns([]);
  }, [loaderData.retryJob]);
  useEffect(() => {
    setDraft((current) =>
      current.row_limit > loaderData.sources.limits.max_rows
        ? { ...current, row_limit: loaderData.sources.limits.max_rows }
        : current,
    );
  }, [loaderData.sources.limits.max_rows]);

  if (catalog === undefined) throw new CatalogError("The catalog could not be loaded.", 500);

  const limits: ImportLimits = loaderData.sources.limits;
  const sourceBytes = new TextEncoder().encode(draft.code).byteLength;
  const livePreview =
    preview?.valid && preview.id !== null && preview.rows_kept > 0 && Date.parse(preview.expires_at) > Date.now();
  const raw = sample?.rows[selectedRow] ?? null;
  const diagnosticLine = preview?.rows.find((row) => row.status === "failed")?.error?.line ?? null;

  function invalidatePreview() {
    previewRequest.current += 1;
    previewAbort.current?.abort();
    previewAbort.current = null;
    setRunningPreview(false);
    setPreview(null);
  }
  function invalidateSource() {
    sampleRequest.current += 1;
    sampleAbort.current?.abort();
    sampleAbort.current = null;
    setLoadingSample(false);
    setSample(null);
    invalidatePreview();
    setError(null);
  }
  const updateSource = (change: Partial<SourceCoordinates>) => {
    setDraft((current) => ({ ...current, source: { ...current.source, ...change } }));
    setSelectedColumns([]);
    invalidateSource();
  };
  const updateCode = (code: string) => {
    invalidatePreview();
    setDraft((current) => ({ ...current, code }));
    setCodeEdited(true);
  };
  const toggleColumn = (key: string) => {
    const selected = selectedColumns.includes(key)
      ? selectedColumns.filter((column) => column !== key)
      : [...selectedColumns, key];
    if (codeEdited) {
      setReplacement({ kind: "columns", columns: selected });
      return;
    }
    setSelectedColumns(selected);
  };
  function confirmReplacement() {
    if (!replacement) return;
    const columns = sample?.columns.map((column) => column.name) ?? [];
    if (replacement.kind === "columns") {
      setSelectedColumns(replacement.columns);
      setDraft((current) => ({ ...current, code: templateFor(replacement.columns, columns) }));
    } else {
      setDraft((current) => ({ ...current, code: templateFor(selectedColumns, columns, replacement.mode) }));
    }
    setCodeEdited(true);
    invalidatePreview();
    setReplacement(null);
  }

  async function loadSample() {
    invalidateSource();
    const requestId = sampleRequest.current;
    const controller = new AbortController();
    sampleAbort.current = controller;
    setLoadingSample(true);
    setError(null);
    try {
      const source = {
        ...draft.source,
        repo_id: draft.source.repo_id.trim(),
        config: draft.source.config?.trim() || null,
        split: draft.source.split.trim(),
        revision: draft.source.revision.trim(),
      };
      const result = await loadSourceSample(source, draft.row_limit, controller.signal);
      if (requestId !== sampleRequest.current) return;
      setDraft((current) => ({ ...current, source }));
      setSample(result);
      setSelectedRow(0);
    } catch (cause) {
      if (requestId === sampleRequest.current) setError(message(cause));
    } finally {
      if (requestId === sampleRequest.current) {
        sampleAbort.current = null;
        setLoadingSample(false);
      }
    }
  }
  async function runPreview() {
    invalidatePreview();
    const requestId = previewRequest.current;
    if (!sample || Date.parse(sample.expires_at) <= Date.now()) {
      setSample(null);
      setPreview(null);
      setError("The source sample expired. Load it again before previewing.");
      return;
    }
    const controller = new AbortController();
    previewAbort.current = controller;
    setRunningPreview(true);
    setError(null);
    try {
      const result = await runDatasetPreview(sample.id, draft.code, controller.signal);
      if (requestId !== previewRequest.current) return;
      setPreview(result);
      setProcessorTab("preview");
      if (!result.valid || result.rows_kept === 0)
        requestAnimationFrame(() => document.getElementById("preview-results-title")?.focus());
      const kept = result.rows.find((row) => row.status === "kept");
      setDraft((current) => ({ ...current, segment_keys: Object.keys(kept?.example?.segments ?? {}) }));
      setSelectedRow(0);
    } catch (cause) {
      if (requestId === previewRequest.current) {
        setError(message(cause));
        setPreview(null);
      }
    } finally {
      if (requestId === previewRequest.current) {
        previewAbort.current = null;
        setRunningPreview(false);
      }
    }
  }
  async function submit() {
    const name = draft.name.trim();
    if (!name) {
      setStep(0);
      setNameError("Enter a dataset name.");
      return;
    }
    if (!livePreview || preview?.id === null || preview === null || Date.parse(preview.expires_at) <= Date.now()) {
      setStep(2);
      setError("Run a fresh, valid preview before importing.");
      return;
    }
    const payload = JSON.stringify({ preview_id: preview.id, name, tags: draft.tags });
    const replay = idempotencyPayload.current === payload && idempotencyKey.current !== null;
    setSubmitting(true);
    setError(null);
    try {
      if (!replay) {
        const latest = await listDatasets(null);
        if (latest.some((dataset) => dataset.name === name)) {
          setStep(0);
          setNameError("A dataset with this name already exists.");
          nameInput.current?.focus();
          return;
        }
      }
      const key = (replay ? idempotencyKey.current : null) ?? crypto.randomUUID();
      idempotencyPayload.current = payload;
      idempotencyKey.current = key;
      const job = await submitImport(preview.id, name, draft.tags, key);
      navigate(`/dataset-imports/${job.id}`);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setSubmitting(false);
    }
  }
  async function continueStep() {
    setError(null);
    setNameError(null);
    if (step === 0) {
      const name = draft.name.trim();
      if (name === "") {
        setNameError("Enter a dataset name.");
        nameInput.current?.focus();
        return;
      }
      if (nameCheck.current !== null) return;
      const controller = new AbortController();
      nameCheck.current = controller;
      setCheckingName(true);
      try {
        const latest = await listDatasets(null, controller.signal);
        if (controller.signal.aborted || nameCheck.current !== controller) return;
        if (latest.some((dataset) => dataset.name === name)) {
          setNameError("A dataset with this name already exists.");
          nameInput.current?.focus();
          return;
        }
        setFurthestStep((current) => Math.max(current, 1));
        setStep((current) => (current === 0 ? 1 : current));
      } catch (cause) {
        if (!controller.signal.aborted && nameCheck.current === controller) setError(message(cause));
      } finally {
        if (nameCheck.current === controller) {
          nameCheck.current = null;
          setCheckingName(false);
        }
      }
      return;
    }
    if (step === 1 && (sample === null || Date.parse(sample.expires_at) <= Date.now())) {
      setError("Load a source sample before continuing.");
      return;
    }
    if (step === 2 && !livePreview) {
      setError("Run a fresh, valid preview before continuing.");
      return;
    }
    if (step === 1 && !codeEdited) {
      const columns = sample?.columns.map((column) => column.name) ?? [];
      setDraft((current) => ({ ...current, code: templateFor(selectedColumns, columns) }));
      setCodeEdited(true);
    }
    setFurthestStep((current) => Math.max(current, Math.min(3, step + 1)));
    setStep((current) => Math.min(3, current + 1));
  }
  function applyTemplate(toolsMode: "none" | "source" | "json") {
    if (codeEdited) {
      setReplacement({ kind: "template", mode: toolsMode });
      return;
    }
    const columns = sample?.columns.map((column) => column.name) ?? [];
    setDraft((current) => ({ ...current, code: templateFor(selectedColumns, columns, toolsMode) }));
    setCodeEdited(true);
    invalidatePreview();
  }
  function rebuildTemplate() {
    applyTemplate("none");
  }
  return (
    <div className="page import-page">
      <header className="topbar import-topbar">
        <nav aria-label="Breadcrumb" className="crumbs">
          <Link to="/datasets">Datasets</Link>
          <span aria-hidden="true">/</span>
          <h1>Add dataset</h1>
        </nav>
      </header>
      <div className="import-body" ref={importBody}>
        <ol aria-label="Import steps" className="import-steps">
          {STEPS.map((label, index) => (
            <li
              aria-current={step === index ? "step" : undefined}
              className={index < step ? "is-done" : undefined}
              key={label}
            >
              <button
                disabled={
                  checkingName || index > furthestStep || (index >= 2 && !sample) || (index === 3 && !livePreview)
                }
                onClick={() => setStep(index)}
                type="button"
              >
                <span className="step-number">{index < step ? <Check size={13} /> : index + 1}</span>
                <span>{label}</span>
              </button>
            </li>
          ))}
        </ol>
        {error ? (
          <p className="alert import-alert" role="alert">
            {error}
          </p>
        ) : null}
        {step === 0 && nameError ? (
          <div className="alert" role="alert" tabIndex={-1}>
            <a href="#dataset-name">Dataset name: {nameError}</a>
          </div>
        ) : null}
        {step === 0 ? (
          <section className="import-card" aria-labelledby="details-heading">
            <header>
              <p className="eyebrow">Step 1 of 4</p>
              <h2 id="details-heading">Dataset details</h2>
              <p>Name the dataset and choose optional catalog tags.</p>
            </header>
            <label className="import-field">
              Dataset name
              <input
                aria-describedby={nameError ? "dataset-name-error" : undefined}
                aria-invalid={nameError ? true : undefined}
                id="dataset-name"
                ref={nameInput}
                autoComplete="off"
                autoFocus
                onChange={(event) => {
                  nameCheck.current?.abort();
                  nameCheck.current = null;
                  setCheckingName(false);
                  setDraft({ ...draft, name: event.target.value });
                  setNameError(null);
                }}
                placeholder="turkish-support-cases"
                value={draft.name}
              />
              {nameError ? (
                <span className="field-error" id="dataset-name-error">
                  {nameError}
                </span>
              ) : null}
            </label>
            <fieldset className="tag-picker">
              <legend>
                Tags <span className="muted">optional</span>
              </legend>
              <p className="hint">Tags classify the whole dataset. Segments classify each example.</p>
              <p className="hint">
                Choose the most specific tags. A child includes its parents; you can choose multiple branches.
              </p>
              <TagPicker
                tags={catalog.tags}
                selected={draft.tags}
                onChange={(path) => setDraft((current) => ({ ...current, tags: toggleTagPath(current.tags, path) }))}
              />
              {draft.tags.length ? (
                <div className="chip-list">
                  {draft.tags.map((tag) => (
                    <button
                      className="filter-chip"
                      key={tag}
                      onClick={() => {
                        idempotencyKey.current = null;
                        setDraft({ ...draft, tags: draft.tags.filter((item) => item !== tag) });
                      }}
                      type="button"
                    >
                      {tag}
                      <X aria-hidden="true" size={12} />
                    </button>
                  ))}
                </div>
              ) : null}
            </fieldset>
            <label className="import-field">
              Source
              <select disabled value="hf_dataset">
                <option value="hf_dataset">Hugging Face</option>
              </select>
            </label>
          </section>
        ) : null}
        {step === 1 ? (
          <section className="import-card" aria-labelledby="source-heading">
            <header>
              <p className="eyebrow">Step 2 of 4</p>
              <h2 id="source-heading">Source and sample</h2>
              <p>Load the first rows to inspect source columns and values. Authentication stays on the server.</p>
            </header>
            <div className="field-grid">
              <label className="import-field">
                Dataset repository
                <input
                  autoComplete="off"
                  onChange={(event) => updateSource({ repo_id: event.target.value })}
                  placeholder="organization/dataset"
                  value={draft.source.repo_id}
                />
              </label>
              <label className="import-field">
                Split
                <input onChange={(event) => updateSource({ split: event.target.value })} value={draft.source.split} />
              </label>
            </div>
            <details className="source-advanced">
              <summary>
                Advanced source settings · {draft.source.config || "default config"} · {draft.source.revision} ·{" "}
                {draft.row_limit.toLocaleString()} row limit
              </summary>
              <div className="field-grid">
                <label className="import-field">
                  Config <span className="muted">optional</span>
                  <input
                    onChange={(event) => updateSource({ config: event.target.value || null })}
                    placeholder="source default"
                    value={draft.source.config ?? ""}
                  />
                </label>
                <label className="import-field">
                  Revision
                  <input
                    onChange={(event) => updateSource({ revision: event.target.value })}
                    value={draft.source.revision}
                  />
                </label>
                <label className="import-field">
                  Source-row limit
                  <input
                    max={limits.max_rows}
                    min={1}
                    onChange={(event) => {
                      setDraft((current) => ({ ...current, row_limit: Number(event.target.value) }));
                      invalidateSource();
                    }}
                    type="number"
                    value={draft.row_limit}
                  />
                  <span className="hint">
                    From 1 to {limits.max_rows.toLocaleString()} rows; sample uses the first {limits.sample_rows} rows.
                  </span>
                </label>
              </div>
            </details>
            <button
              className="button-ghost"
              disabled={
                loadingSample ||
                !draft.source.repo_id.trim() ||
                !draft.source.split.trim() ||
                !draft.source.revision.trim() ||
                !Number.isInteger(draft.row_limit) ||
                draft.row_limit < 1 ||
                draft.row_limit > 10000
              }
              onClick={() => void loadSample()}
              type="button"
            >
              {loadingSample ? <LoaderCircle className="spin" size={14} /> : <RotateCcw size={14} />}Load sample
            </button>
            {sample ? (
              <div className="sample-summary">
                <p>
                  {sample.rows.length} sample rows · revision <code className="mono">{sample.source.revision}</code>{" "}
                  resolved to <code className="mono">{sample.resolved_sha}</code>
                </p>
                <p className="hint">Sample expires {new Date(sample.expires_at).toLocaleString()}.</p>
                <div className="source-columns">
                  <h3>Columns</h3>
                  {sample.columns.map((column) => (
                    <span className="filter-chip" key={column.name}>
                      <code>{column.name}</code>
                      <small>{column.types.join(" | ") || "unknown"}</small>
                    </span>
                  ))}
                </div>
                <fieldset className="segment-picker">
                  <legend>Use source columns as segments</legend>
                  <p className="hint">
                    Selected columns are added to the starter processor as string values. You can add custom segments in
                    the next step.
                  </p>
                  {sample.columns.map((column) => {
                    const valid =
                      /^[A-Za-z_][A-Za-z0-9_]*$/.test(column.name) && !RESERVED_SEGMENT_KEYS.includes(column.name);
                    return (
                      <label key={column.name} className={valid ? "" : "is-invalid"}>
                        <input
                          type="checkbox"
                          checked={selectedColumns.includes(column.name)}
                          disabled={!valid}
                          onChange={() => toggleColumn(column.name)}
                        />
                        <code>{column.name}</code>
                        {!valid ? <span className="hint">This name cannot be used as a segment key.</span> : null}
                      </label>
                    );
                  })}
                </fieldset>
                <RawSample rows={sample.rows} selected={selectedRow} select={setSelectedRow} />
              </div>
            ) : null}
          </section>
        ) : null}
        {step === 2 ? (
          <section className="import-card processor-card" aria-labelledby="processor-heading">
            <header>
              <p className="eyebrow">Step 3 of 4</p>
              <h2 id="processor-heading">Processor and preview</h2>
              <p>
                Python maps each raw source row into a conversation, available tools, output and segments. Return the
                same segment keys with string values for every retained row.
              </p>
              <p>
                To add a custom segment, add an entry to the processor's <code>segments</code> dictionary, for example{" "}
                <code>"difficulty": "hard" if row["score"] &gt; 5 else "easy"</code>.
              </p>
            </header>
            <details className="processor-contract">
              <summary>Execution restrictions</summary>
              <p>
                Return <code>None</code> to skip a row. Only the supported Python subset runs in the isolated processor.
                Definitions in <code>tools</code> are data; the processor cannot execute them. It has no filesystem,
                network, OS, or host-call access.
              </p>
            </details>
            <fieldset className="processor-tabs" aria-label="Processor workspace">
              {(["input", "processor", "preview"] as const).map((tab) => (
                <button
                  className="control-button"
                  key={tab}
                  type="button"
                  aria-pressed={processorTab === tab}
                  onClick={() => setProcessorTab(tab)}
                >
                  {tab === "input" ? "Input" : tab === "processor" ? "Processor" : "Preview"}
                </button>
              ))}
            </fieldset>
            <div className="processor-layout" data-tab={processorTab}>
              <div className="source-sample-pane">
                <RawSample compact rows={sample?.rows ?? []} selected={selectedRow} select={setSelectedRow} />
                <ToolSourcePreview row={raw} />
              </div>
              <div className="processor-code">
                <div className="processor-toolbar">
                  <strong>Python processor</strong>
                  <details className="processor-templates">
                    <summary>Replace with a starter template</summary>
                    <p className="hint">
                      Choose how the template should read the source row's <code>tools</code> field. This replaces the
                      entire processor.
                    </p>
                    <div className="processor-template-options">
                      <div>
                        <button className="button-ghost button-small" onClick={rebuildTemplate} type="button">
                          No tools
                        </button>
                        <span>Always return an empty tools list.</span>
                      </div>
                      <div>
                        <button
                          className="button-ghost button-small"
                          onClick={() => applyTemplate("source")}
                          type="button"
                        >
                          Tools as a list
                        </button>
                        <span>Use the source tools field directly.</span>
                      </div>
                      <div>
                        <button
                          className="button-ghost button-small"
                          onClick={() => applyTemplate("json")}
                          type="button"
                        >
                          Tools as JSON text
                        </button>
                        <span>Parse the source tools field if it is a JSON string.</span>
                      </div>
                    </div>
                  </details>
                </div>
                <ProcessorEditor diagnosticLine={diagnosticLine} onChange={updateCode} value={draft.code} />
              </div>
            </div>
            <div className="processor-actions">
              {preview && preview.rows_kept === 0 ? (
                <p className="warning-note">
                  All sampled rows were skipped. Retain at least one sample row to determine the segment keys.
                </p>
              ) : null}
            </div>
            <p className="hint">
              Processor source: {sourceBytes.toLocaleString()} / {limits.max_source_bytes.toLocaleString()} bytes.
            </p>
            <div className="processor-preview" data-tab={processorTab}>
              {preview ? (
                <PreviewResults preview={preview} selected={selectedRow} select={setSelectedRow} />
              ) : (
                <p>Run preview to see results.</p>
              )}
            </div>
          </section>
        ) : null}
        {step === 3 ? (
          <section className="import-card" aria-labelledby="review-heading">
            <header>
              <p className="eyebrow">Step 4 of 4</p>
              <h2 id="review-heading">Review import</h2>
              <p>Check the pinned source, processor, segments and row-level output before import.</p>
            </header>
            <ReviewSummary draft={draft} sample={sample} preview={preview} onEdit={setStep} />
            <p className="warning-note">
              Sample results do not guarantee full-import success. If any source row fails, the complete import is
              rejected without publishing a partial dataset.
            </p>
            {error ? (
              <p className="alert" role="alert">
                {error}
              </p>
            ) : null}
          </section>
        ) : null}
        <footer className="import-navigation">
          <button
            className="button-ghost"
            disabled={step === 0 || submitting || runningPreview || loadingSample}
            onClick={() => {
              setError(null);
              setStep((current) => current - 1);
            }}
            type="button"
          >
            <ArrowLeft size={14} />
            Back
          </button>
          <span>{step + 1} / 4</span>
          <div className="import-next-actions">
            {step === 2 && (
              <Button
                variant="primary"
                type="button"
                loading={runningPreview}
                disabled={sample === null || sourceBytes > limits.max_source_bytes}
                onClick={() => void runPreview()}
              >
                Run preview
              </Button>
            )}
            {step < 3 ? (
              <Button
                variant={step === 2 ? "secondary" : "primary"}
                disabled={checkingName || (step === 1 && sample === null) || (step === 2 && !livePreview)}
                onClick={continueStep}
                type="button"
              >
                {step === 2 ? "Continue to review" : "Continue"}
                <ArrowRight size={14} />
              </Button>
            ) : (
              <Button
                variant="primary"
                loading={submitting}
                disabled={!livePreview}
                onClick={() => void submit()}
                type="button"
              >
                {submitting ? "Starting import…" : "Import dataset"}
              </Button>
            )}
          </div>
        </footer>
      </div>
      <Dialog
        open={replacement !== null}
        title="Replace processor code?"
        description="This replaces the current processor code and invalidates its preview."
        onClose={() => setReplacement(null)}
      >
        <Button autoFocus type="button" onClick={() => setReplacement(null)}>
          Cancel
        </Button>
        <Button type="button" onClick={confirmReplacement}>
          Replace code
        </Button>
      </Dialog>
    </div>
  );
}

function RawSample({
  rows,
  selected,
  select,
  compact = false,
}: {
  rows: Array<Record<string, unknown>>;
  selected: number;
  select: (index: number) => void;
  compact?: boolean;
}) {
  if (!rows.length) return <p className="hint">Load a source sample to inspect raw rows.</p>;
  return (
    <section aria-label="Raw source rows" className={`raw-sample ${compact ? "is-compact" : ""}`}>
      <div className="raw-tabs" role="tablist" aria-label="Sample row">
        {rows.map((_, index) => (
          <button
            aria-selected={selected === index}
            className="button-ghost button-small"
            key={index}
            onClick={() => select(index)}
            role="tab"
            type="button"
          >
            Row {index + 1}
          </button>
        ))}
      </div>
      <pre className="raw mono">{JSON.stringify(rows[selected], null, 2)}</pre>
    </section>
  );
}
function ToolSourcePreview({ row }: { row: Record<string, unknown> | null }) {
  const tools = row?.tools;
  return (
    <details className="source-tools">
      <summary>Source tool data</summary>
      <pre className="raw mono">{JSON.stringify(tools ?? [], null, 2)}</pre>
    </details>
  );
}
function PreviewResults({
  preview,
  selected,
  select,
}: {
  preview: DatasetPreview;
  selected: number;
  select: (index: number) => void;
}) {
  return (
    <section className="preview-results" aria-labelledby="preview-results-title">
      <div className="preview-head">
        <h3 id="preview-results-title" tabIndex={-1}>
          Preview rows
        </h3>
        <span>
          {preview.rows_kept} kept · {preview.rows_dropped} skipped ·{" "}
          {preview.rows.filter((row) => row.status === "failed").length} failed
        </span>
      </div>
      <div className="preview-rows">
        {preview.rows.map((row, index) => (
          <button
            aria-pressed={selected === index}
            className="preview-row"
            key={row.source_index}
            onClick={() => select(index)}
            type="button"
          >
            <strong>Source row {row.source_index + 1}</strong>
            <span data-status={row.status}>{row.status}</span>
            {row.error ? (
              <span>
                {row.error.message}
                {row.error.line ? ` (line ${row.error.line})` : ""}
              </span>
            ) : null}
          </button>
        ))}
      </div>
      {preview.valid ? (
        <PreviewExample row={preview.rows[selected] ?? null} />
      ) : (
        <p className="alert" role="alert">
          Preview failed validation. Fix the processor before continuing.
        </p>
      )}
    </section>
  );
}
function PreviewExample({ row }: { row: DatasetPreview["rows"][number] | null }) {
  if (!row) return null;
  if (row.status === "skipped")
    return <p className="hint">This processor intentionally skipped the selected source row.</p>;
  if (row.status === "failed")
    return (
      <p className="alert" role="alert">
        {row.error?.message ?? "The row failed."}
      </p>
    );
  return (
    <div className="preview-example">
      <h4>Normalized example · source row {row.source_index + 1}</h4>
      <pre className="raw mono">{JSON.stringify(row.example, null, 2)}</pre>
      <AvailableTools key={row.source_index} tools={row.example?.tools ?? []} />
    </div>
  );
}
function ReviewSummary({
  draft,
  sample,
  preview,
  onEdit,
}: {
  draft: Draft;
  sample: SourceSample | null;
  preview: DatasetPreview | null;
  onEdit: (step: number) => void;
}) {
  const keptRows = preview?.rows.filter((row) => row.status === "kept") ?? [];
  const [row, setRow] = useState(0);
  return (
    <div className="review-summary">
      <section>
        <h3>
          Dataset{" "}
          <button onClick={() => onEdit(0)} type="button">
            Edit
          </button>
        </h3>
        <dl>
          <dt>Name</dt>
          <dd>{draft.name.trim()}</dd>
          <dt>Tags</dt>
          <dd>{draft.tags.join(", ") || "None"}</dd>
        </dl>
      </section>
      <section>
        <h3>
          Source{" "}
          <button onClick={() => onEdit(1)} type="button">
            Edit
          </button>
        </h3>
        <dl>
          <dt>Repository</dt>
          <dd>{draft.source.repo_id}</dd>
          <dt>Config / split</dt>
          <dd>
            {draft.source.config ?? "default"} / {draft.source.split}
          </dd>
          <dt>Revision</dt>
          <dd>
            {draft.source.revision} → {sample?.resolved_sha}
          </dd>
          <dt>Rows</dt>
          <dd>{draft.row_limit}</dd>
        </dl>
      </section>
      <section>
        <h3>
          Segments{" "}
          <button onClick={() => onEdit(2)} type="button">
            Edit processor
          </button>
        </h3>
        <p>{draft.segment_keys.join(", ") || "None"}</p>
      </section>
      <section>
        <h3>
          Processor{" "}
          <button onClick={() => onEdit(2)} type="button">
            Edit
          </button>
        </h3>
        <p>
          SHA-256 <code className="mono">{preview?.source_hash}</code>
        </p>
        <pre className="raw mono review-code">{draft.code}</pre>
        <p>
          {preview?.rows_kept} kept · {preview?.rows_dropped} skipped in sample.
        </p>
      </section>
      <section>
        <h3>Sample output</h3>
        {keptRows.length ? (
          <>
            <label className="import-field">
              Review kept row
              <select
                onChange={(event) => setRow(Number(event.target.value))}
                value={Math.min(row, keptRows.length - 1)}
              >
                {keptRows.map((entry, index) => (
                  <option key={entry.source_index} value={index}>
                    Source row {entry.source_index + 1}
                  </option>
                ))}
              </select>
            </label>
            <PreviewExample row={keptRows[Math.min(row, keptRows.length - 1)] ?? null} />
          </>
        ) : (
          <p className="warning-note">Run a preview that retains at least one sample row before continuing.</p>
        )}
      </section>
    </div>
  );
}
function templateFor(keys: string[], columns: string[], toolsMode: "none" | "source" | "json" = "none") {
  const textColumn = columns.includes("text") ? "text" : (columns[0] ?? "text");
  const outputColumn = columns.includes("label") ? 'row.get("label")' : "None";
  const segments = keys
    .map(
      (key) =>
        `            ${JSON.stringify(key)}: ${columns.includes(key) ? `str(row[${JSON.stringify(key)}])` : '"REPLACE_ME"'}`,
    )
    .join(",\n");
  const toolSetup =
    toolsMode === "json"
      ? '    tools = row.get("tools", [])\n    if isinstance(tools, str):\n        tools = json.loads(tools)\n'
      : "";
  const toolValue = toolsMode === "none" ? "[]" : toolsMode === "source" ? 'row.get("tools", [])' : "tools";
  const importJson = toolsMode === "json" ? "import json\n\n" : "";
  return `${importJson}def process(row: dict) -> dict | None:\n${toolSetup}    # Return None to intentionally skip a source row.\n    return {\n        "conversation": [\n            {"role": "user", "content": row[${JSON.stringify(textColumn)}]}\n        ],\n        "tools": ${toolValue},\n        "expected_output": ${outputColumn},\n        "segments": {\n${segments}${segments ? "\n" : ""}        },\n    }\n`;
}
function message(error: unknown) {
  return error instanceof Error ? error.message : "The dataset import request failed.";
}
export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  return (
    <div className="page">
      <header className="topbar">
        <h1>Add dataset</h1>
      </header>
      <div className="page-body">
        <CatalogAlert error={error} />
      </div>
    </div>
  );
}
