# Inference runs with configurable OpenAI-compatible endpoints

Status: Implemented as a Develop/PoC feature. Primary implementers: GPT-6.1 Terra subagents, medium reasoning effort. Local execution trail: `.audit/inference-runs/decisions.jsonl` (root agent is the sole writer).

## Goal

Send one assistant-continuation request per stored dataset row to a user-managed Chat Completions endpoint. Each run evaluates one model across multiple datasets selected directly or through tags. Deliver saved connection profiles, execution limits, common controls plus arbitrary JSON parameters, dataset output defaults with a visual JSON Schema builder, durable results, cancellation, and explicit resume.

Scoring, tool execution, and media inference are outside this release. Preserve existing dataset/import/tag behavior. No commits or deployment are requested.

## Approved decisions

- Profiles save name, base URL, model, and optional server API-key environment-variable reference. Never persist key values in profiles or run records or return them to the browser.
- Profile reasoning modes are Effort levels or Thinking on/off. Server default omits the reasoning parameter, so a Neither mode is unnecessary. Effort controls configure allowed strings and a request-body path; thinking controls configure a boolean request-body path. Show only supported controls; Server default omits the parameter. Do not infer capabilities from model names or translate off into an effort value.
- Optional generation fields: maximum generated tokens, temperature, top-p, seed. Profile selects max_completion_tokens or max_tokens. Nested advanced JSON supplies arbitrary additional request-body fields. Reject conflicts with common controls and protected fields (model, messages, row tools, output format, streaming, response count). One completion, no streaming.
- Show credential-free effective request preview. Explicit Test example sends a selected row and shows response, timing, and validation. Disable tests while an inference run is active.
- Dataset output metadata supports Text, JSON object, JSON Schema. Existing datasets default to Text. It is mutable metadata; never rewrite immutable snapshots. Allow separate run overrides per dataset and freeze effective settings in the run.
- Shared Visual/JSON schema editor supports paste/upload/download, nested objects/arrays/scalars, enums, descriptions, required and nullable fields. Canonical JSON is the source of truth. Unsupported visual constructs remain intact in JSON and disable visual editing with an explanation.
- Object-root schemas, optional strict mode defaulting on. Strict mode requires all properties and additionalProperties=false recursively, using nullable values for optional values. Non-strict schemas may have optional properties. Backend Draft 2020-12 validation, no remote reference fetching. Local schema validity does not imply endpoint compatibility.
- Send response_format, preserve raw response plus parsed data and validation errors. Distinguish refusal, truncation, malformed JSON, schema mismatch, and tool-call-only output. No format downgrade or answer-regeneration retries.
- Inference module owns request compilation, transport, scheduling, durable storage. Use current-only catalog initialization, application lifecycle and generated API contracts. Do not add backward-compatibility code.
- Public contracts: ConnectionProfile, OutputFormat, RunSpec, RunView, RowResult. API supports profile CRUD, dataset output read/update, request tests, run create/list/detail, paged results, cancel, resume.
- Freeze dataset IDs/names, snapshot identities, profile/generation settings, and output formats at creation. Resolve tag selection to explicit IDs; later tag/profile/schema changes cannot alter runs.
- Batch source reads, preserve retained ordinal and source_index. Serialize tool-call arguments to JSON strings, send stored conversations and row tools, never gold answers or injected prompts. Preflight all inputs before enqueueing: media and unsupported history fields produce dataset/source-row diagnostics. Historical thinking input is explicitly unsupported in v1 because its representation is provider-specific.
- One active inference run per catalog; queue others. Concurrency/RPM are shared across all datasets in the active run. Count every attempt. SDK retries disabled; scheduler owns retries and accounting. Retry transport/timeouts, 429, 5xx with bounded backoff and Retry-After support.
- SQLite incrementally persists raw JSON, content/tool calls, parsed output, validation status, finish reason, available usage, latency, attempts and sanitized errors. Never execute tool calls. Individual request failures do not stop remaining rows; authentication failure stops the run.
- Startup marks unfinished runs interrupted; no automatic paid requests on recovery. Explicit resume skips committed results; a crash may require resending an in-flight request. Cancel stops dispatch and active requests; keep partial results.
- After dataset purge retain copied dataset ID/name, generated results and frozen run metadata, not duplicated input conversations/expected outputs/extras. Viewer shows missing inputs as unavailable. Transactionally block permanent deletion for queued/running/interrupted dependent runs until completed or canceled. Trash alone must not break already-selected rows.
- Navigation: Connections, Inference runs. Setup: datasets -> configuration -> review. Results grouped by dataset with progress and error filters; keyboard access, responsive layout and both themes.
- Defaults: 4 concurrent requests, 60 RPM, 120-second timeout, 2 retries, unset generation fields, all rows of each selected dataset. Request tests are optional.

## Implementation units

- [x] U1: Typed contracts, current schema initialization, profile storage, dataset output metadata and deletion guard. Verify current schema initialization, rejection of unsupported formats and independent metadata changes.
- [x] U2: Schema validation, request compilation, source-row batching and transport. Verify exact wire bodies, role/tool conversion, unsupported-input diagnostics, conflicts and secrets.
- [x] U3: Durable single-runner scheduling, limits/retries/cancel/recovery/resume, incremental results. Verify with a local fake HTTP Chat Completions server.
- [x] U4: API routes, application lifecycle, generated contracts and runtime frontend parsing. Verify request errors, CRUD, tests, paged results and deletion lifecycle.
- [x] U5: Connection editor, visual/JSON schema editor and dataset integration. Verify modes, schema preservation, strict validation, keyboard/narrow/both-theme behavior.
- [x] U6: Run setup/list/detail/results, frozen settings, grouped progress, cancel/resume/test. Verify full browser workflow against real local API and fake endpoint.
- [x] U7: Documentation and final repository checks. Record actual results and remaining limitations; no unverified completion claims.

## Verification

- [x] Reasoning modes, omission/defaults, nested mappings, parameter conflicts, token mapping, credentials.
- [x] Visual/JSON round trips, nested/strict schemas, unsupported constructs, dataset overrides.
- [x] Actual local HTTP request serialization, mixed dataset limits and retries, transient/permanent failures, cancellation, restart/resume, committed-row deduplication.
- [x] Schema mismatches/refusals/truncation/tool calls remain inspectable; frozen runs survive configuration edits.
- [x] Purge is blocked for unfinished runs; completed history survives purge; current-format backup/restore preserves profiles and results.
- [x] Browser setup/results, accessibility, narrow viewports, light/dark themes.
- [ ] Backend tests/lint/format/types, frontend tests/lint/format/types/build/browser tests, generated contract and docs checks as documented in docs/how-to/develop-and-test.md.

## Evidence and implementation constraints

- Dataset rows remain immutable Parquet; SQLite catalog schema is now version 5. Older schemas are rejected without upgrades. DatasetRepository.purge owns deletion and must enforce new dependency guards before removing files.
- Existing examples() does not expose source_index; introduce a suitable ID-based bounded reader without changing existing callers.
- Workbench is React 19 / React Router 8 / TypeScript with CodeMirror, shared dialogs, fields, tags, IBM Plex fonts and semantic light/dark tokens. Extend established UI patterns.
- Added locked direct dependencies for openai>=3.42.0, jsonschema and referencing>=0.37.0. Existing export_contract.py must include inference routes and accurately express the new JSON contracts.
- Existing backup copies SQLite and referenced Parquet; keeping inference metadata/results in SQLite preserves the backup boundary.
- Official sources consulted: https://developers.openai.com/api/reference/python and https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat . SDK supports extra_body, explicit max_retries=0; strict schemas require all properties and disallow additional properties. Provider compatibility is verified by explicit endpoint tests.

## Develop verification and remaining limits

The user explicitly selected Develop/PoC depth and requested no further detailed audits. Implementation units are complete; the unchecked full-suite verification item above records the inherited failure rather than claiming a clean suite.

- Final Linux full backend suite: 207 passed, 1 failed. The same tag-deletion test fails on isolated unchanged HEAD (195 passed, 1 failed). It expects the old TagInUseError behavior; tag behavior was not changed for inference.
- After test signature/narrowing corrections, all-project Python lint, formatting, types, generated-contract and docs checks pass, and all 12 inference tests pass. Local logs: .audit/inference-runs/linux-pytest.log and linux-final-checks.log.
- Frontend lint, formatting, types and all 16 unit tests pass. Production build and all 5 new inference browser tests pass against a local API and fake completion endpoint, including 61-result server-side paging, independent invalid schema drafts, nested schema edits and narrow/light/dark views. The complete legacy browser suite was not run.
- No real model endpoint, production catalog, commit or deployment was used. Existing host services were left running. Disposable Linux verification container is removed at handoff.

User follow-up: no backward-compatibility code is permitted during development. Removed all catalog/profile upgrades, format-1 snapshot reads, name-based HTTP aliases and old import-version acceptance. Bundled demo data uses the current format.
