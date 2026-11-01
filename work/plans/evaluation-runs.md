# Evaluation of saved inference results

Status: Implementation in progress. Mode: Execute. Profile: Develop / PoC. An isolated ten-row exact-match workflow and local fake judge have been exercised. The checklist and verification notes below distinguish completed work from outstanding acceptance items.

## Goal

Evaluate saved inference responses using exact match or an LLM judge, calculate named numeric scores, and inspect means and coverage overall and by dataset, segment and tag. Reuse saved predictions. A developer adding a methodology must not edit scheduling, persistence, aggregation or generic results UI.

Success is a complete ten-example workflow from a completed inference run through setup, preview, scoring test, execution and evidence inspection. Automated verification uses a local fake judge, not a paid service or GPU benchmark.

## Constraints and user decisions

- One Markdown prompt area owns all instructions, rubric and examples. Variable insertion and rendered preview are supporting controls, not separate editable prompts.
- Reuse the existing visual/JSON structured-output tool for judge results.
- A scoring function receives a result dictionary and returns named finite integers/floats. Test discovers keys; optional ranges/direction appear in a table. Mean is the only initial aggregate.
- Optional candidate preprocessing preserves raw output and cannot access references/extras.
- Implement exact match and LLM judge. Math equivalence and code execution are future extension examples, not implementations. No pairwise judging, composite scores, calibrated probabilities, confidence intervals or threshold tuning.
- Trusted code methods can use their own dependencies. Editor-authored code stays in capability-free Monty, with no host eval/exec, external callbacks or CPython fallback.
- User chose **main catalog database plus a fresh catalog reset**, not a sidecar. No migrations, old-version readers or compatibility aliases.
- User chose **references with deletion guards** to limit storage. Completed scores/evidence survive deletion of source inputs; inspection then reports unavailable.
- Preserve the current uncommitted inference run-deletion changes in store/routes/UI/tests.
- Planning authorizes this file only. Do not reset catalogs, restart services or issue judge requests in this turn. During later implementation use isolated catalogs first. A fresh reset removes existing datasets, history and profiles. Never reset implicitly at startup. The previous instruction to preserve active inference still governs activation timing if work is running.

## Findings

Paths below are repository-relative. Backend paths with package-relative prefixes are under src/llm_evaluation_hub/.

| Concern | Verified evidence | Consequence |
| --- | --- | --- |
| Current schema | core/datasets/catalog/schema.py:_create_schema, version 5 | Add current schema v6; old nonempty catalogs remain rejected. Rebuild seed and reset local catalog explicitly. |
| Row identity | core/datasets/catalog/repository.py:inference_rows | Bounded ID reader has ordinal/source_index, but intentionally strips reference/extras/segments. Add a separate evaluation reader. |
| Full records | DatasetRepository.examples | Reuse decoding, not the name-based API which loses source_index. |
| Purge | DatasetRepository.purge uses BEGIN IMMEDIATE and purge_pending | Extend transactional dependency checks; evaluation creation rejects pending purge. |
| Inference deletion | Uncommitted InferenceStore.delete_run | Preserve and extend with unfinished-evaluation guard. |
| Judge transport | inference/compiler.py:compile_request, validate_format; transport.py:send, interpret | Reuse profile/generation/schema and real transport/retry/classification. |
| Python runtime | imports/runtime.py:ProcessorRunner | Hardcodes process(row) and ProcessedExample. Extract only neutral Monty mechanics. |
| Scheduling | inference/runner.py:Runner, RateLimiter; api/app.py:create_app | Follow lifecycle, bounded tasks, owner lock, incremental writes and recovery. No universal job-framework rewrite. |
| Structured editor | web/app/features/inference/output-editor.tsx:OutputEditor | Move implementation to shared ownership and migrate all callers. Preserve visual/JSON behavior. |
| Python editor | web/app/features/dataset-imports/processor-editor.tsx:ProcessorEditor | Move to shared PythonEditor with configurable label; retain diagnostics/themes. |
| Markdown | No existing Markdown editor/dependency | Add a focused Markdown source editor, no rich-text framework. |
| Routing/contracts | web/app/routes.ts, shell.tsx, scripts/export_contract.py | Add evaluation routes/nav/router export; regenerate API declarations. |
| Backup | scripts/catalog_backup.py | Main SQLite already belongs to backup boundary; add evaluation round-trip assertion. |

Read docs/modules/inference.md, docs/architecture/code-map.md, docs/how-to/develop-and-test.md and work/plans/inference-runs.md for existing contracts. New paths named below are proposed, not existing APIs.

## Decisions

### Population and identity

One evaluation run targets one **terminal** inference run and a nonempty subset of its frozen datasets. Completed/canceled/interrupted source runs are selectable. Queued/running/canceling are not. Block source resume while an unfinished evaluation references it, so the prediction population cannot change during evaluation.

Population is all retained ordinals of selected datasets in the source manifest. Before creation show selected rows, available successful predictions and unscorable rows. Missing predictions/non-ok inference statuses become committed source-ineligible outcomes, not judge calls or zeros. A canceled source with 36 successful predictions out of 500 therefore has at most 36/500 score coverage. No hidden successful-only selection. Freeze source_result_present and source_status for every input. After evaluation ends, resuming an interrupted inference run may add new predictions, but those cannot retroactively become eligible in this evaluation or appear as its original candidate. Existing committed inference results use INSERT OR IGNORE and remain immutable; no prediction-body copy is needed.

Join by (source inference run ID, dataset ID, retained ordinal), verify source_index, never use name/response text/list order. Add bounded DatasetRepository.evaluation_rows(dataset_id, offset, limit) returning full ProcessedExample plus ordinal/source_index. Include trashed snapshots, reject purge_pending and unsupported format. Keep inference_rows gold-free. Extract only shared decoding needed by full readers.

Freeze dataset ID/name/path/snapshot version/tag paths and per-row identity/segment values plus prediction presence/status at evaluation creation. Tag attribution reflects creation time, not original inference time. Do not copy conversation, reference, full prediction/raw response or rendered prompt per row. Persist new method judgments, scores and raw judge evidence. Render source-input/request previews on demand while sources exist.

Creation refuses already-purged/unreadable snapshots. Missing reference is allowed if unused. Exact match requires non-null expected_output; missing values are source-ineligible. Unknown prompt paths are configuration errors. Known extra/segment paths absent/null on an otherwise eligible row must be reported in preflight; edit prompt or narrow dataset selection before creation. Never silently insert empty text.

### Definitions and frozen runs

A reusable named EvaluationDefinition holds method ID/version/config, optional preprocessing, scoring source and metric declarations. CRUD saves its current draft. Saving/deleting it never changes existing runs. Setup allows selecting a saved definition or saving inline; no separate definition wizard is required.

EvaluationRun freezes the full definition, selected datasets, resolved judge connection/generation/schema, source run identity, attribution and execution limits. One definition/scoring contract applies to all selected datasets. Metric name alone identifies that metric across the run. No per-dataset renaming or evaluator-version barriers inside a run. Combining independent evaluation runs is deferred.

### Preprocessing and exact match

Optional preprocess(response: dict) -> JsonValue receives only {content, parsed, tool_calls}. No example, reference, extras, tags or segments. Disabled means candidate=response.content. Null content requires explicit extraction of another usable representation, never empty-string coercion. Preserve raw input separately. Apply once before method evaluation.

Exact match has empty config initially. Strings compare verbatim. Objects ignore key order; arrays preserve order; JSON types are distinct (bool differs from number; string differs from number), while finite JSON numbers use numeric equality (1 equals 1.0). Null reference is ineligible. No implicit stripping, case folding or math extraction. A custom candidate preprocessor can normalize/extract; reference transformations/equivalence require a future method.

Judgment is {"matches": boolean}; default score returns {"correctness": int(result["matches"])} with optional range 0..1, higher-is-better. Explain that MATH-500's explanation responses will often fail against short answers unless the user extracts the candidate answer. Do not implement math extraction heuristics in exact match.

### Judge prompt and output

One CodeMirror Markdown source area, cursor insertion, allowed-field picker and selected-row Rendered prompt view. Add @codemirror/lang-markdown. Display substituted Markdown as text. No HTML execution; formatted Markdown rendering is optional, not a gate.

Backend owns literal {{path}} placeholders, with allowlist/catalog:

- conversation (original conversation serialized as JSON)
- response.content, response.parsed, response.tool_calls
- processed_response
- expected_output
- extras.<key>, segments.<key> from observed fields

No expressions, loops, filters, execution or recursive interpolation. Strings insert literally; nonstrings use deterministic finite JSON. Preserve LaTeX/backslashes and all other text. Unknown paths block validation. Known fields missing on a dataset/ordinal produce actionable diagnostics as described above. Unused fields are not required. Starter prompt says candidate text is data, not instructions to obey.

Compile one user message with rendered text; no dataset tools forwarded. Select existing connection plus Generation settings. Judge defaults: no reasoning control sent, max output 1024, concurrency 1, RPM 60, timeout 120s, two transient retries. Review exposes these editable limits. Reuse OutputEditor but require object-root JSON Schema for this method; no prose-number parsing. Default strict schema: required correct:boolean and reason:string, additionalProperties=false. Default score maps correct to correctness 0/1.

Compile via existing compile_request with an explicitly constructed judge-only ProcessedExample. Reuse send/interpret with a temporary in-memory RowResult transport envelope, translating status/evidence to MethodOutcome. Never persist it as model inference or duplicate the SDK transport. This bounded adapter avoids a broad shared-transport rewrite. Invalid JSON/schema, refusal and truncation never reach score(). No repair prompts or semantic retries. Existing transient transport retry policy applies; authentication interrupts the run.

### Scoring and metric declaration UI

score(result: dict) -> dict[str, int | float] sees only the validated method result dictionary. Require a nonempty dictionary, nonempty string keys and finite numeric values. Reject bool values, NaN/Infinity, strings, null and nested values. Boolean judgments must be explicitly converted with int().

Test method previews preprocessing and judgment. Exact match is local; a judge test explicitly sends one request. Preview the credential-free effective request first, then show raw response, parsed judgment, status, usage and latency. Also allow manually supplied result JSON for scoring tests without a model call; schema-validate it and label it synthetic, never an observed judgment.

Test scoring executes code on a valid selected result and discovers the metric table: read-only name, preview value, optional min/max, higher/lower direction (higher default), aggregation Mean (fixed). No separate name entry. Bounds are finite with min <= max; reject out-of-range scores without clamping. Direction affects display only. No automatic normalization. Code or result-schema edits invalidate discovery; bounds/direction edits revalidate existing values. Retest retains metadata for unchanged keys and flags removed keys.

Saving/creating is disabled until a scoring test matches current source/result contract. This is UI validation, not a new durable attestation framework. API callers can supply explicit declarations; backend validates config/source and enforces the exact declared key set and numeric/range rules on every row. A failed scoring row stores no partial metric dictionary. Do not union keys across outputs or silently vary denominators per metric.

### Method extensibility and module cohesion

Proposed package src/llm_evaluation_hub/evaluation/ owns contracts, registry, store, runner, scoring/preprocessing adapters, prompts, aggregation and methods/. Scheduler never branches on method IDs.

Proposed method contract:

- MethodDefinition: stable ID, integer version, label, Pydantic config model/schema, result-schema resolver, default scoring source/metric metadata, and resource capability local or model_endpoint. Every result is a JSON object; exact match declares its matches:boolean schema, judge uses its configured schema, and a custom method can initially declare a permissive object schema.
- resolve_config(config, services) -> frozen JSON config: default validates/returns config; judge resolves profile ID to a credential-free profile snapshot here. Run creation calls this generic hook, with no method-ID branch. Resolve result schema from the frozen config and persist it with the run. Validate method results and manually supplied test results against that schema before scoring.
- open(config, services) -> AsyncContextManager[EvaluationSession]: prepare resources once per run and release on completion, error, cancellation and interruption.
- await session.evaluate(context) -> MethodOutcome: context includes full example, original response, processed candidate and stable identities. Outcome has a finite JSON-object result plus optional raw method evidence, timing, attempts and usage. Only result goes to score(). A custom method can return MethodOutcome(result={...}) without fabricating judge fields.
- Methods validate configuration and own their substantive evaluation/preparation/cleanup. Common runner owns eligibility, preprocessing, score validation, persistence and recovery. Use typed safe row/infrastructure failures; valid negative judgments are successful evaluation outcomes.
- Services inject limits/credential resolution/client resources, not FastAPI globals. Resolve judge connection to a frozen profile at creation; credentials remain environment names, never values.

Adding a method requires one module and one registry entry with config/default scoring. Expose config JSON Schema/defaults in method metadata. Generic JSON config editing and generic result JSON inspection must work without frontend changes. Optional custom config editors can be registered separately. Use method_id as an extensible string and method config as a JSON object validated through the registry, not a central literal-only union of built-in configs. No dynamic user-path imports, hot reload, dependency installer, entry-point discovery or marketplace.

A future coding evaluator prepares its isolated harness in open(), compiles/runs/tests in evaluate(), returns {compiled, tests_passed, tests_total, all_tests_passed}, and closes resources afterward. Compilation failure is a valid negative result; broken harness infrastructure is an evaluator error. No code execution implementation or subprocess shortcut now. Prove the seam with a tiny test-only custom method, not a real math/coding method.

Extract neutral Monty worker verification, fresh-session execution, finite JSON budgets, resource limits and diagnostics into proposed execution/python.py. Generic runner accepts a fixed validated entrypoint and JSON input. Import ProcessorRunner remains an import-domain adapter validating ProcessedExample or None; evaluation validates JSON candidate/score dictionary. Move RateLimiter to execution/rate_limit.py and migrate inference callers. Delete moved duplicate implementations, not compatibility wrappers. Do not refactor other import/inference logic.

### Aggregation and evidence

Report each metric mean over fully valid scored rows, with scored count and selected count. Also expose pending, failed and source-ineligible counts; coverage=scored/selected. Missing/invalid judgments have no numeric score. Zero scored rows means null mean / No valid scores, not zero. While running, label summaries partial and distinguish pending from failures.

Example: 10 selected, 7 scores=1, one score=0, two judge failures means .875 at 8/10 coverage and two failures. Never present .7 as the same metric or .875 as coverage. Bounds do not change aggregation arithmetic.

Group controls: Overall, Dataset, Segment (choose key), Tag. Use frozen names/segment values/tag paths. Mean is over examples, not equally weighted dataset averages. Deduplicate selection by dataset ID and ordinal. A dataset participates once in each matching tag group, including ancestors of frozen paths, but once in an overall union. Never sum overlapping tag groups as the total. Missing segment/untagged identity is null internally with display labels, not a string that collides with real values.

Use backend SQL or bounded accumulators; never calculate from a single browser page or load all raw response payloads for summaries. Use one shared scope contract for results and summaries: optional dataset IDs and tag paths, combined as dataset membership AND any matching tag (each omitted filter accepts all). Expand tags against frozen paths. Segment selection changes grouping only, with no segment drill-down in v1. Status is a separate Rows only display filter; it does not change means, coverage or denominator. Label this explicitly in the UI. A shared scope change updates both summary and row requests. Each input has one committed outcome, including source-ineligible and failed results, so progress/resume is deterministic.

### Persistence and retention

Current schema v6 adds these proposed tables to catalog.sqlite:

| Table | Minimum records/constraints |
| --- | --- |
| evaluation_definitions | ID, name, current settings JSON, timestamps |
| evaluation_runs | ID, historical source_inference_run_id, frozen settings/profile/method version JSON, state/total/timestamps/error |
| evaluation_run_datasets | PK(run_id,dataset_id), frozen name/path/format/row count/tag paths JSON |
| evaluation_inputs | PK(run_id,dataset_id,ordinal), source_index, source_result_present, source_status, segments JSON; small immutable eligibility manifest |
| evaluation_results | same input PK, stage/status, method result JSON, nullable scores JSON, nullable raw judge/method evidence, safe error, timing/attempts/usage |

FKs within evaluation-owned tables; child-first transactional deletion. No retention/cascade FK to source inference, dataset, definition or profile because completed history must survive deletion. Index source run and dataset dependencies for deletion guards. Avoid duplicating identical judge output inside both result and raw evidence unnecessarily.

Creation uses a single main-database BEGIN IMMEDIATE: check terminal source state and snapshot availability, freeze settings/identity/attribution, preflight required variables/source alignment and commit queued run atomically. Scan Parquet in bounded pages. Existing purge_pending is rejected. The write transaction prevents a deletion/resume from beginning before dependencies are committed. In inference Runner.resume, explicitly BEGIN IMMEDIATE before both the unfinished-evaluation dependency check and the source state update, closing the race against evaluation creation. No model requests inside the transaction. On failure roll back and report dataset/row diagnostics. Do not create 500 network calls as preflight.

Extend DatasetRepository.purge and InferenceStore.delete_run in their owning transactions: queued/running/canceling/interrupted evaluation dependency blocks source deletion. Extend inference Runner.resume similarly, checking dependency in the same state update transaction. After evaluation completed/canceled allow deletion, retain scores/judge evidence/grouping and return explicit input-unavailable for missing source inspections. Trashing alone keeps source access. Changed/deleted tags cannot rewrite history.

Delete an inactive evaluation run with confirmation: atomically remove results, input manifest, dataset manifest and run. Reject queued/running/canceling with 409, allow interrupted deletion. Definition deletion does not delete runs; source deletion does not delete evaluations. Pages become reusable in SQLite; do not promise immediate physical compaction or add automatic VACUUM.

### Runner and recovery

One evaluation runner owns .evaluation.lock and one active evaluation run per catalog. Follow existing background event-loop thread/lifespan cleanup and bounded task patterns. One run's concurrency/RPM limits cover all its datasets, with every HTTP attempt counted.

A model_endpoint method acquires the existing inference runner's thread-safe admission lock for the entire run, including explicit judge test. Queue while inference/test owns it and display waiting for model endpoint. Use admission.acquire(blocking=False) with cancellation-aware async waits, never a blocking lock acquisition on the event-loop thread. Recheck queued/cancel state before dispatch and release admission in finally even if method opening fails. Explicit judge tests return 409 when admission is busy rather than waiting indefinitely. Local exact-match does not acquire that lock. This protects the local GPU without endpoint/GPU probing or a universal job framework. Lifecycle start/stop must close already-open components if later initialization fails.

Cancel stops dispatch/cancels active tasks/closes method context, preserving committed outcomes. Startup converts queued/running to interrupted and canceling to canceled, with no automatic requests. Resume only interrupted, skip all committed outcomes including failures, verify method/version/source availability. Canceled cannot resume. Authentication or run resource unavailability interrupts; per-row failure continues. Exactly one committed outcome per identity; a crash may resend an uncommitted in-flight external request. Never claim exactly-once network execution.

## Plan

Each unit ends with an observable result. Boxes are checked only where the implementation and its stated check have been verified. An implementer reads the complete plan and existing diff first, keeps a local ignored show-me-your-work trail and checks units only after verification. The parent integrates; any delegated implementer must own explicit files and preserve other changes.

### U1. Contracts, shared execution and method seam

Owner: backend/core. No dependencies.

- [ ] Add evaluation contracts/registry with typed built-in configurations, source context, MethodOutcome, metric/settings/status/summary models. Registry exposes schemas/defaults and generic method metadata. No UI-specific state in domain objects.
- [x] Extract neutral Monty execution and rate limiter into execution/. Migrate current import/inference callers without budget/diagnostic changes. Add preprocessing/scoring validation and literal prompt renderer.
- [ ] Implement exact match and a test-only custom method proving prepare/evaluate/cleanup with no scheduler branch.

Check: exact-match and scoring work on JSON fixtures; invalid numeric types/keys/ranges fail clearly. Custom method lifecycle runs. Focused import-runtime and existing inference limiter tests still pass. Avoid speculative abstractions and unrelated refactoring.

### U2. Schema, source reader and store

Owner: backend/persistence. Depends on U1 contracts.

- [ ] Add v6 schema/tables/indexes, store CRUD and atomic run creation. Add bounded full evaluation_rows reader and retain inference_rows gold isolation.
- [ ] Add purge/source-delete/source-resume guards, inactive evaluation deletion and historical input availability.
- [x] Rebuild bundled seed as a **fresh v6 catalog** using public registration APIs and existing current-format Parquet examples as fixture input. Retain all five starter names/content/tags. A temporary artifact rebuild can read old seed metadata read-only for fixture names/tags; it must not become a runtime v5 reader, data migration or upgrade path. Remove obsolete reconstruction code after regeneration if not reusable.

Check: isolated current catalog freezes aligned identities, protects unfinished sources, allows source deletion after completion/cancel and retains report evidence. Seed initializes a disposable target and every snapshot reads correctly. Do not touch the live catalog.

### U3. Judge implementation and runner

Owner: backend/execution. Depends on U1/U2.

- [ ] Add methods/llm_judge.py owning frozen profile config, rendered prompt, structured request, transport adapter and evidence. Scoring remains common.
- [ ] Add runner with run-scoped method lifecycle, shared endpoint admission, limits/counted retries, incremental writes, cancellation and explicit recovery.
- [ ] Wire create_app lifecycle/state with cleanup if any component fails; no endpoint requests on startup.

Check: local fake HTTP judge receives correct rendered values/schema/frozen settings and no dataset tools. Valid false judgment scores zero; invalid schema/JSON, timeout and scoring errors retain stage-specific evidence. Cancel closes context; resume skips committed work. Keep one focused lifecycle integration rather than duplicating the inference scheduler test suite.

### U4. Aggregation and API

Owner: backend/API. Depends on U2/U3.

- [ ] Add api/evaluation_routes.py and router. Proposed endpoints: GET /evaluation-methods; CRUD /evaluation-definitions; POST /evaluations/preview, /evaluations/test-method, /evaluations/test-scoring; POST/GET /evaluations; GET/DELETE /evaluations/{id}; POST /evaluations/{id}/cancel|resume; GET /evaluations/{id}/results, /summary, /inputs/{dataset_id}/{ordinal}.
- [ ] Preview/test uses complete draft config and source run/dataset/ordinal. Preview sends no request; method test explicitly sends one; scoring test accepts validated result JSON + code. Return processed value, applicable credential-free rendered request, judgment, diagnostics and score discovery.
- [ ] Server page results with offset/limit and the shared dataset/tag scope contract. Summary uses the same scope plus group_by=overall|dataset|segment|tag and segment_key. Status filtering is labeled Rows only and affects result pages, not summaries. Segment selection groups only. Deduplicate before arithmetic; never drop errors from coverage.
- [ ] Return 404 unknown IDs, 409 lifecycle/dependency conflict, 422 invalid config/schema/code, safe row-stage diagnostics. Include router in export_contract.py and regenerate API types.

Check: arithmetic fixture yields .875 with 8/10 coverage, consistent cross-dataset keys, overlapping-tag dedup, missing-group bucket and null empty mean. Registered test method is usable with JSON config and generic result evidence without backend API conditionals.

### U5. Shared editors and evaluation setup

Owner: frontend/editor. Depends on U1 wire contracts/U4 API.

- [ ] Move actual OutputEditor to shared/output-editor.tsx with shared/generated Output type. Migrate inference runs, dataset-output and dataset import callers and delete old module. Preserve Visual/JSON strict-schema behavior, unsupported schemas and value replacement. Numeric bounds can remain JSON-only; do not expand the visual schema editor first.
- [ ] Move ProcessorEditor to shared/python-editor.tsx as PythonEditor with configurable accessible label; migrate import caller. Retain theme, history, diagnostics and controlled value changes.
- [ ] Add evaluation/api.ts using generated types plus boundary parsers; prompt-editor.tsx; metric-table.tsx; method-config.tsx with two built-in controls and generic JSON fallback; new.tsx. Do not add another feature into large inference/runs.tsx.
- [ ] Wizard: Source (terminal run/datasets and selected/available/missing counts) -> Method (saved/new definition, optional preprocessing, judge prompt/profile/generation/schema or method JSON config) -> Preview and scoring (selected example, request preview/test, Python scoring, discovered metrics) -> Review/run. Exact match comes with default scoring. Save/reuse a definition inline. Explicit tests are the only preview-stage network requests.

Check: one Markdown prompt, variable insertion at cursor, rendered text, existing structured tool, test-discovered read-only metric names, working bounds/direction, stale/invalid drafts block creation. One contract applies across datasets. Registered custom method works with generic JSON config and result inspection. One narrow/theme spot check; no visual redesign.

### U6. Navigation, history and evidence

Owner: frontend/results. Depends on U4/U5.

- [ ] Add Evaluations desktop/mobile navigation and /evaluations, /evaluations/new, /evaluations/:id in routes.ts. Add Evaluate results link to terminal inference RunDetail with source ID query parameter. Preserve uncommitted Delete run action. New setup can select a source if opened directly.
- [ ] Separate list.tsx/detail.tsx: state/progress/waiting reason, overall means and scored/selected/pending/failure counts, Dataset/Segment/Tag group controls, segment-key picker and server-paged rows. Frozen settings disclosure. Keep state/request wiring out of pure table components.
- [ ] Row inspector shows original/processed/reference if source available, method result/scores/raw judge output/latency/attempts/stage error. Missing inputs are explicit while retained evidence stays inspectable. Render text/JSON safely, not raw HTML.
- [ ] Cancel, interrupted Resume and inactive Delete with ConfirmDialog; explain dependency conflicts on source deletion. Updating definitions never changes frozen run reports.

Check: same metric across two datasets, failed judgment remains in coverage counts, source deletion availability is clear, inactive evaluation deletion removes its artifacts but keeps source data. A plugin needs no custom result UI.

### U7. Focused checks, docs and activation handoff

Owner: integrating implementer. Depends on U1-U6.

- [ ] Complete verification below, review diff for metric/data invariants and preserved prior changes, update this plan and local decision trail with actual evidence.
- [x] Update new docs/modules/evaluation.md plus docs/index.md, docs/project/purpose.md, docs/modules/api.md, docs/architecture/code-map.md and affected import/inference runtime references. Document method registration, contract/coverage semantics, current-schema reset, retention and deferred math/code execution. Keep documentation proportional.
- [ ] Build images without restarting live services. Prepare a concrete fresh reset/start procedure naming Compose project/volume. Clearly state the reset removes all existing catalog datasets/history/profiles; model container/cache is separate and stays. No silent startup migration/reset. If an active run remains under the prior preserve-running instruction, leave images ready and ask for activation timing.
- [ ] After separately authorized activation, verify fresh schema and seed, create/import a ten-row fixture and demonstrate exact match. Judge smoke uses a fake local endpoint; actual vLLM usage is an explicit bounded test. Do not run a 500-row evaluation as verification.

## Verification: Develop / PoC

Get one thin end-to-end path visible first, then finish targeted guard checks. Tests protect data and metric meaning, not an artificial coverage percentage. No full legacy browser sweep, mutation testing, benchmark campaign, Thermos/release audit or unrelated cleanup. Broader delivery checks are deferred until a shared-release request or a concrete newly exposed failure.

- [ ] Backend focused checks: full-row ID alignment and gold-free inference reader; score finite types/key set/bounds; literal prompt parsing; exact match; deterministic ten-row aggregation with overlap/missing segments; atomic source purge/delete/resume guards; retained evidence after source deletion.
- [ ] One tiny real-local-HTTP integration covers actual judge wire schema, valid/invalid judgments, incremental persistence, cancel/cleanup and interrupted resume. Assert endpoint admission with a controlled test, not a GPU throughput experiment. Prove a registered test method executes without scheduler/storage/UI branches.
- [x] Existing focused tests/imports runtime checks and relevant tests/test_inference.py checks cover shared runtime/limiter extraction. New evaluation tests live in tests/evaluation/. Keep failure permutations in backend tests rather than duplicating them all in browser tests.
- [ ] Add isolated web/e2e/evaluation.spec.ts with real API and fake completion endpoint: saved inference -> exact match -> score discovery -> grouped results; judge Markdown variable insertion + shared schema -> two metric keys across two datasets; one invalid result changes coverage; cancel deletion dialog then confirm. Use scripts/serve_test_catalog.py fixtures. Retain existing inference browser smoke for editor moves and prior deletion work. One narrow/light-dark spot check is sufficient.
- [x] Focused Ruff lint/format and ty for changed/new owners; frontend typecheck/build and focused Biome; generated API contract check; docs link check. Report inherited failures separately; don't broaden this task to fix unrelated tests.
- [x] WSL/Linux for locking/runtime. Node >=22.22 is required; available /home/nusret/.nvm/versions/node/v22.23.4/bin/node. Default /usr/bin/node can be too old. Isolate browser ports with WORKBENCH_TEST_API_PORT and WORKBENCH_TEST_WEB_PORT. Do not stop/reuse localhost:8080 or vLLM:8001 for automated tests.
- [ ] Final handoff records demonstrated behavior, actual check results, reset/deployment status and limits. Technical integration does not establish judge accuracy; a ten-row demo is not a benchmark-quality claim.

## Handoff and completion boundary

Accepted product choices: main database with fresh reset, reference retention with deletion guards, one prompt, shared structured tool, scoring-derived metric names, shared aggregation and cohesive code extension. Other defaults above deliberately bound v1: one source run per evaluation, exact match first, fixed mean, literal variables, integer/float scores and ten-row demonstration.

Read AGENTS.md, this plan and working-tree diff before editing. During authorized implementation apply show-me-your-work, keep its trail local/ignored, and maintain this file as decisions change. Delegation prompts must state unit, dependencies, exact file ownership, this plan path and that implementers are not alone and must preserve other edits. Contracts must stabilize before backend/frontend parallel implementation; assign editor moves and inference deletion guards to single owners. If evidence contradicts this plan, update the affected unit and report the consequence before expanding scope.

Planning completion checklist:

- [x] Inspect runtime/editor/transport reuse, identity, purge and lifecycle.
- [x] Resolve main database versus sidecar with the user.
- [x] Resolve reference versus copied-input retention with the user.
- [x] Specify contracts/UI/extensibility/aggregation and implementation units.
- [x] Read-only backend/frontend handoff review and final consistency pass. Resolved generic config/result-schema ownership, frozen prediction eligibility, cancelable endpoint admission, resume/create serialization and row/summary filter scope.

No remaining material product question is intentionally delegated to the implementer. Changes to accepted semantics need feedback; routine private symbol names/layout can follow repository conventions.


## Execution evidence and remaining work

- The final focused backend set passed **63 tests**, including nine evaluation tests for numeric score contracts, exact match, literal prompts, source guards, 8/10 coverage with mean 0.875, fake HTTP judge responses, registered method execution, backup and retained evidence, cancellation, endpoint admission, overlapping tags, missing segments and interrupted resume.
- The isolated evaluation browser smoke passed against the final build. The existing inference/editor browser smoke passed before the last evaluation-only changes. The parent directly inspected and approved setup, schema, report, dark/mobile layout, discovered extra/segment fields, processed-candidate inspection and generation controls. An isolated ten-row exact-match UI run completed 10/10.
- Focused Ruff lint, Python types, frontend typecheck, focused Biome lint, generated API contract and documentation link checks passed. The final frontend and both Compose images built successfully without restarting live services.
- The judge prompt picker discovers observed extras and segments. Its generation settings include temperature, top-p, seed, profile-specific effort/thinking and bounded advanced JSON. Row inspection presents the processed candidate separately. A rendered judge prompt is shown as text.
- The two-dataset/two-metric judge browser scenario remains deferred; local HTTP judge, registered-method and backend aggregation checks cover the component contracts, but do not establish that complete browser scenario or judge accuracy. A ten-row demo is not a benchmark.
- The isolated preview is at `http://127.0.0.1:18733`; it uses a disposable API catalog on port 18731. A pre-created completed report is at `/evaluations/470dafbe-c8dd-4883-b8f3-788dba52c584`. These preview processes are separate from the live services.
- Activation remains separately authorized. Compose project is `llm-evaluation-hub`, catalog volume `llm-evaluation-hub_catalog`. After confirming activation timing and taking any needed backup, the concrete fresh-start procedure is `docker compose down`, `docker volume rm llm-evaluation-hub_catalog`, then `LLM_EVAL_SEED=/opt/llm-eval/seed docker compose up -d` from the repository. This permanently removes existing catalog datasets, inference/evaluation history and connection profiles. The model service and model cache are separate. Never perform it while an active inference run must be preserved.
