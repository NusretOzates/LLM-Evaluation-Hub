# Frontend, backend, and documentation refactor plan

## Goal

Improve the catalog's correctness, maintainability, frontend reliability, and documentation through small, verifiable changes. This is a review and implementation plan, dated 2026-10-26. Implementation is complete within the approved local Linux scope. See implementation status for verified results; the findings preserve the original baseline. The baseline audit covers the current source, tests, configuration, containers, and documentation, rather than a pull-request diff.

Success means supported datasets and tags remain accessible, publication cannot erase unrelated files, UI navigation has regression protection, transport contracts stay aligned, ordinary reads avoid initialization work, and contributors can run and recover the system using maintained instructions.

## Constraints

Preserve the current Python registration library, FastAPI service, SQLite metadata, Parquet snapshots, React Router SPA, and existing documentation layout. Preserve source ordering, zero-based source indices, one-based displayed rows, row count meanings, exact segment declarations, leading-system normalization, source provenance, credential exclusion, descendant tag filtering, and idempotent tag links. Do not add evaluation/training workflows: this repository is currently a dataset catalog.

Do not combine this work with dependency upgrades, a framework replacement, an ORM migration, a general repository abstraction, or an authentication product. Keep application behavior changes explicit and separate them from file moves. No production datasets are needed for regression tests. Use synthetic catalogs and sanitized message fixtures.

No AGENTS.md was found in the repository search. Git reports work/ as untracked, with no tracked changes shown; Windows Git also emitted a sequencer filesystem error, so this is not a fully reliable Git-state audit. The original review made no application changes. Implementation now includes locked dependency setup, code changes, regression tests and documentation. No commits or deployment to an existing catalog are authorized or performed.

## Baseline review evidence and limits

This table records the original review before implementation. Current verification results are recorded in Implementation status. The review included independent correctness/security and maintainability passes, followed by lead inspection. All findings below are baseline issues or risks, not changes introduced by this task. Source references use repository-relative paths and symbols so they remain useful after line shifts.

| Check | Actual result | Limit |
| --- | --- | --- |
| Source and test inspection | Reviewed API, catalog, record/processing/source boundaries, frontend routes/client/shell/styles, deployment, documentation and tests | Static inspection does not prove runtime or browser behavior |
| Documentation link scan | Four relative links target missing docs/data/snapshot.md | Checked Markdown file targets, not anchors, remote URLs, or complete OKF conformance |
| JavaScript special-key probe | Node v24.22.1 reproduced assignment of __proto__ yielding no own enumerable key and JSON {} | Minimal executable reproduction of the same dictionary operation, not a browser end-to-end test |
| Seed probe | Actual ensure_starter_catalog removed an unrelated sentinel in an isolated temporary target | Sandbox denied the final rename; publication success, crash durability and concurrency remain unverified |
| Python test/lint/type baseline | Not executed | WSL returned Wsl/E_ACCESSDENIED; available native Python is 3.11, below >=3.12, without pytest, Ruff, ty, Polars or FastAPI |
| Frontend typecheck/build/browser baseline | Not executed | web/node_modules absent; no dependency provisioning performed |
| Container smoke | Not executed | No running Docker verification attempted |

## Findings

Priorities: P1 requires early attention to data/trust boundaries. P2 is a correctness, contract, or maintainability improvement with concrete impact. P3 is bounded structural cleanup. Act on means evidence supports including the work; it does not mean a production failure was observed.

| ID | Priority and disposition | Evidence and consequence | Unit |
| --- | --- | --- | --- |
| F1 | P1, Act on | api/seed.py:ensure_starter_catalog calls _clear_directory when catalog.sqlite is absent. _clear_directory deletes every child, including unrelated files. The isolated probe confirmed sentinel deletion. Concurrent publishers can also interfere because the existence check has no lock. | U3 |
| F2 | P1, Act on | api/app.py:create_app permits all CORS origins, methods, and headers on unauthenticated dataset reads and tag mutations. An unrelated origin that can reach the API is allowed access. Loopback binding does not establish an origin trust boundary. Browser private-network controls can affect exploitability. | U2 |
| F3 | P2, Act on | catalog/repository.py:_validate_request permits slash-containing dataset names, but api/routes.py uses a single {name} segment. Such registered names can be listed but cannot reliably reach detail/examples routes. encodeURIComponent does not solve ASGI slash decoding. | U4 |
| F4 | P2, Act on | web/app/catalog.ts:tagForest and parseTagForest assign arbitrary legal keys into {}. __proto__ changes the object's prototype instead of adding an own key. Tags can disappear or serialize as an empty forest. Inspect all domain-keyed dictionaries, including segment parsing. This is not evidence of arbitrary code execution. | U1 |
| F5 | P2, Act on | web/app/routes/dataset.tsx:RowIndex retains a selected facet across page/dataset transitions; controls disappear when the next page has <=1 or >8 facet values. A stale filter can hide all rows with no visible reset. | U1 |
| F6 | P2, Act on | web/package.json has no test/lint/format scripts. No CI workflow was found. Backend tests exist, but frontend pagination, selection, parsing, mutations, and shortcuts have no automated behavioral protection. | U0 |
| F7 | P2, Act on | docs/index.md, docs/modules/api.md, docs/modules/core.md and docs/architecture/overview.md link to missing docs/data/snapshot.md. The central stored-row and message contract is unavailable to readers. git check-ignore -v confirms .gitignore:12 data/ also excludes docs/data/snapshot.md, so restoring it without correcting ignore scope would leave the contract untracked. | U0, U10 |
| F8 | P2, Act on | web/app/catalog.ts duplicates backend transport shapes, models message roles as arbitrary strings, and substitutes empty extras/segments for malformed values. Backend records.py has role-specific models. Drift can be hidden and rendering repeatedly inspects unknown shapes. | U5 |
| F9 | P2, Act on | dataset.tsx is 690 lines spanning routing, actions, state, filtering, display and formatting. It imports shared hooks from shell.tsx and formatters from routes/datasets.tsx, coupling feature logic to UI entry points. | U6 |
| F10 | P2, Act on | catalog/repository.py:_connection performs directory creation, WAL setup and schema DDL for every read/write connection. Separate initialization from normal operations while retaining create-if-missing constructor behavior. | U7 |
| F11 | P2, Consider | list_datasets maps _record per dataset, and _record loads tag paths separately. Root and child loaders duplicate dataset/tag requests; TagSection repeatedly scans datasets for counts. Scaling cost is evident, but production latency has not been measured. | U8 |
| F12 | P2, Act on | shell.tsx:useStoredFlag has unguarded localStorage operations; dataset.tsx:RowViewer has unhandled clipboard rejection; readIndex accepts digit-only values without Number.isSafeInteger. These browser/URL failure paths need explicit behavior. | U1 |
| F13 | P2, Consider | register writes Parquet then commits SQLite. It compensates for ordinary insert errors but process death between file publication and insert can leave orphans. Existing tests cover insert failure and WAL reopening, not process-kill recovery or concurrent publication. | U3, U7 |
| F14 | P3, Consider | app.css is 1,350 lines across shell/list/inspector and responsive rules. It already has tokens, focus rules, breakpoints and reduced-motion support. Align style ownership with feature extraction without redesigning the visual system. | U9 |
| F15 | P2, Act on | Existing docs have useful navigation and module references but lack a contributor check recipe and complete SQLite-plus-Parquet backup/recovery procedure. Docker instructions use down -v without an immediate explicit backup/data-loss prerequisite. | U10 |
| F16 | P2, Consider | api/app.py handles every ValueError as a client 422. Unexpected stored-row decoding/validation errors can be misclassified as invalid requests and their messages returned to clients. Distinguish request-domain errors from corrupt storage/internal failures. | U5 |

Paths beginning api/ or catalog/ in this table are under src/llm_evaluation_hub/api/ and src/llm_evaluation_hub/core/datasets/catalog/ respectively.

## Decisions

Keep the existing architecture. The repository is small enough that direct module ownership is preferable to service/repository wrappers around every method. Keep DatasetRepository as the public facade, TagStore as a connection-bound collaborator, and domain processing independent of HTTP.

Address concrete defects before extraction. Keep tests focused on observable contracts, including saved data and real routes; do not mirror private helper implementations. Preserve existing meaningful tests rather than replacing them wholesale.

Retain runtime validation at the HTTP boundary and an authoritative backend transport contract. Generated TypeScript transport types are the recommended direction for U5; generation does not replace runtime parsing. Keep arbitrary JSON typed as JSON values or unknown where the domain actually allows it.

Preserve the current OKF documentation structure. Restore the missing contract first and update existing documents in the same unit that changes behavior or paths. Do not defer all documentation until the end or rewrite historical provenance as newly verified.

Measure scaling work before changing public list responses or adding caches. Batch known redundant SQL work first. Streaming registration and dataset-list pagination require workload evidence and remain conditional.

## Plan

The checkbox represents implementation completion, not review completion. U0 through U10 are implemented and verified. Conditional workload-dependent changes remain explicitly excluded. Owners below are responsibilities for future work, not spawned implementation agents. Sizes are relative: S is one focused change, M spans a few related modules, L needs several separately reviewable changes. Resolve the decision gates below before their dependent units.

### U0. Establish a reproducible baseline and repair documentation navigation

Owner: quality/documentation. Dependencies: none. Size: M. Priority: immediate.

- [x] Run existing backend checks and frontend typecheck/build in the supported Linux/Python >=3.12 environment using the committed locks. Record baseline failures separately from new regressions.
- [x] Add frontend behavioral test tooling with a small parser/URL suite and one real-browser catalog-to-row flow. Add frontend lint/format commands and a CI workflow that runs existing Python checks and frontend checks without paid/network dataset calls.
- [x] Restore docs/data/snapshot.md from records.py, processing.py, repository.py and tests, covering schema, JSON/null semantics, row ordering, count identities, segment restrictions, tag paths, provenance and message variants. Narrow the root data ignore rule or explicitly unignore docs/data/ so the contract is trackable; preserve exclusion of runtime catalogs. Verify with git check-ignore and git status.
- [x] Add a local Markdown target-link check. Validate required concept frontmatter separately from link quality. Give every new check one documented command.

Files: .gitignore; pyproject.toml and uv.lock only if selected test dependencies require changes; web/package.json and package-lock.json; new frontend tests/config and CI files; docs/data/snapshot.md; docs/index.md and existing code map. Proposed new tool/file names are implementation choices, not existing files.

Acceptance: a clean supported checkout can install from locks and reproduce checks; CI runs backend tests plus frontend tests/typecheck/build; all four missing-target links resolve. Baseline failure reporting must not label unavailable checks as passing. Do not block urgent U1/U2/U3 fixes on unrelated cleanup.

### U1. Fix frontend domain-key handling, state transitions, and browser failures

Owner: frontend. Dependencies: U0's focused test harness. Size: M. Findings: F4, F5, F12.

- [x] Use safe own-property construction for arbitrary domain keys consistently in tag creation, response parsing, and relevant segment dictionaries. Preserve legal names rather than banning __proto__ as a workaround.
- [x] Scope facet/query state explicitly to dataset/page identity. Reconcile a facet when available values change, and expose a clear/reset control whenever a filter is active.
- [x] Validate URL/jump indices as safe integers with valid bounds before issuing requests. Return the existing understandable invalid-position error presentation.
- [x] Make localStorage optional: preserve in-memory preferences when reads/writes fail. Handle unavailable/denied clipboard calls with visible feedback and no unhandled rejection.

Files: web/app/catalog.ts; web/app/routes/dataset.tsx:RowIndex, RowViewer, readIndex; web/app/shell.tsx:useStoredFlag; frontend regression tests; docs/modules/workbench.md.

Acceptance: __proto__, constructor and toString survive create/parse/serialize/display; crossing to a page with one different facet never produces an invisible active filter; switching datasets resets state by the specified rule; huge indices fail locally; denied storage/copy leaves browsing usable. Verify keyboard navigation across page boundaries.

### U2. Define and enforce the local API trust boundary

Owner: backend/deployment. Dependencies: origin-policy decision D1. Size: S to M. Finding: F2.

- [x] Default the proxy-based workbench to same-origin access. If direct cross-origin development is needed, configure an explicit allowlist with validated configuration at the application boundary.
- [x] Test permitted and unrelated Origin/preflight responses and document that CORS governs browser access, not authentication. Keep the existing loopback-only Compose publication.
- [x] If the service must become multi-user or remotely reachable, open a separate authenticated deployment design before exposing it. Do not treat an origin allowlist as authorization for nonbrowser clients.

Files: src/llm_evaluation_hub/api/app.py and asgi.py; tests/api/; compose.yaml if configuration must pass through; docs/configuration/runtime.md, docs/modules/api.md, local/Docker recipes.

Acceptance: the documented workbench works through its proxy; unrelated origins receive no permissive browser CORS grant; direct API clients remain consistent with the chosen trust contract. Confirm behavior through HTTP headers rather than only inspecting middleware configuration.

### U3. Make starter publication safe and recoverable

Owner: persistence/runtime. Dependencies: D2 publisher/platform contract. Size: L. Findings: F1, F13.

- [x] Reject seed/target equality and overlapping paths before touching target data. Stage payload and consistent SQLite backup inside an explicitly owned staging location.
- [x] Serialize publishers using a mechanism valid on supported filesystems; recheck target state under ownership before publishing. Coordinate initialization with catalog creation, not just two seed callers.
- [x] Treat an existing database as authoritative. Reject unrelated preexisting content when no database exists; cleanup may remove only artifacts provably owned by this initialization protocol.
- [x] Validate database integrity and referenced snapshot availability before publication. Retain publish-database-last semantics and define what happens after interruption at each stage.
- [x] Add tests using two real processes and injected interruption points. Include seed=target, overlapping paths, unrelated sentinel, existing edits, missing/corrupt payload, and restart scenarios.

Files: api/seed.py, api/asgi.py, tests/api/test_seed.py; a narrow persistence collaborator only if shared initialization ownership requires it; docs/configuration/runtime.md and docs/how-to/run-with-docker.md.

Acceptance: unrelated content survives a rejected initialization; simultaneous starts converge to one complete catalog; a retry never removes an existing user's committed catalog; every published database references available snapshots. Filesystem crash durability is a distinct requirement from Python exception recovery and must be claimed only to the supported level.

### U4. Align dataset identity across registration, API, and URLs

Owner: backend/frontend contract. Dependencies: D3 identity compatibility decision. Size: M. Finding: F3.

- [x] Inventory existing accepted names and callers without reading private row payloads. Choose an identity contract and record it before route changes.
- [x] Recommended option: use the existing immutable dataset UUID for transport identity and keep names as unrestricted display/registration identities. Define route shape and compatibility for existing name links before implementation.
- Alternative considered and rejected: constrain names to a route-safe grammar. UUID transport preserves the existing accepted display-name domain.
- [x] Migrate repository lookups, API routes, frontend links/loaders/client methods, tests and docs together. If external name URLs require compatibility, make the retention/removal boundary explicit; otherwise remove obsolete internal callers in the same unit.

Files: catalog/repository.py; api/routes.py; tests/api/test_dataset_routes.py and catalog tests; web/app/catalog.ts and both dataset routes; docs/modules/api.md, core.md and workbench.md.

Acceptance: slash-containing display names, Unicode, percent signs, question marks and hash characters either round-trip through supported identity routes or are rejected at the owning boundary under the accepted grammar. Existing catalog records and intended bookmarks remain usable under the approved compatibility policy.

### U5. Strengthen transport contracts and error ownership

Owner: API/frontend boundary. Dependencies: U0; finalize after U4 identity decision. Size: M. Findings: F8, F16.

- [x] Export a deterministic backend OpenAPI contract and derive frontend transport types, or document a deliberately synchronized equivalent if generation adds more cost than value. Pin generation tooling when introduced and check generated drift in CI.
- [x] Preserve role-specific message variants, typed content parts and tool calls. Keep runtime response parsing at request(), reject invalid required shapes, and retain arbitrary expected_output/extras values without lossy coercion.
- [x] Separate transport/model declarations, runtime parsing and HTTP operations only where each has clear ownership. Avoid a second handwritten domain model that repeats generated types.
- [x] Use explicit request-domain validation errors for 422 handling. Let corrupt storage and internal errors produce generic server failures with useful server-side diagnostics, excluding tokens and raw conversation data.
- [x] Carry loader cancellation signals through requests where useful; distinguish intentional aborts from API-unreachable errors.

Files: api/schemas.py, app.py and routes.py; core catalog error types where owned; web/app/catalog.ts and new contract/parser files as justified; API/client tests; docs/modules/api.md and data/snapshot.md.

Acceptance: valid backend examples for every role/content/tool variant parse and render; malformed required values fail visibly; 404/422/network/non-JSON/500 paths have stable presentation; server failures do not leak raw internals; generated contract updates are reproducible. Do not claim type generation establishes runtime data validity.

### U6. Give frontend features coherent ownership

Owner: frontend. Dependencies: U1 and U5 contracts; U0 browser baseline. Size: M. Finding: F9.

- [x] Keep dataset.tsx responsible for route exports, loading/action coordination, and feature composition. Move the inspector's row list/viewer, tag manager and metadata presentation into a cohesive feature area.
- [x] Move position/filter/message transformations into testable feature-owned modules. Move genuinely shared formatters and browser hooks out of route/shell entry points.
- [x] Use React Router's generated route argument types for route exports where available. Keep state beside the component/feature that owns it; do not add global state management without a demonstrated cross-route need.
- [x] Keep each extraction behavior-preserving and remove obsolete imports/helpers after migration. Avoid one-file-per-tiny-function fragmentation.

Files: web/app/routes/dataset.tsx, datasets.tsx, shell.tsx and root.tsx; proposed web/app/features/dataset-inspector/, shared hooks/format modules; tests; docs/architecture/code-map.md and docs/modules/workbench.md.

Acceptance: no detail-route dependency on the list route for formatting or shell component module for generic hooks; direct links/back/forward, row-only changes without refetch, page crossing, tag revalidation, JSON view, copy, errors and empty states retain specified behavior. Judge readability by tracing one row-navigation path, not by a mandatory file-size threshold.

### U7. Separate persistence initialization from operations

Owner: backend persistence. Dependencies: U3 ownership/recovery contract. Size: M. Findings: F10, F13.

- [x] Keep constructor create-if-missing behavior but move schema initialization and persistent WAL setup to explicit idempotent initialization. Keep foreign_keys, timeout and transaction cleanup with ordinary connections.
- [x] Define detection of incompatible schema versions before destructive or mutating work. Add a minimal version marker only if evolution requires it; do not introduce a general migration framework without a real migration.
- [x] Keep registration's filesystem/SQLite state transitions explicit. Define orphan detection and a report-first reconciliation procedure after process death. Never auto-delete unclassified files on ordinary reads.
- [x] Exercise real SQLite/Parquet persistence, rollback, duplicate-name races and restart behavior. Preserve the existing public DatasetRepository facade and imports.

Files: catalog/repository.py; focused connection/publication module only if it reduces responsibilities; tests/datasets/catalog/test_repository.py; docs/modules/core.md and architecture/overview.md.

Acceptance: normal reads execute no schema DDL; reopen retains existing data; failed writes leave no advertised partial dataset; concurrent duplicate registration has a defined domain outcome; orphan diagnosis reports precisely what can be recovered or removed. Test filesystem and SQL failure stages separately.

### U8. Remove measured redundant work

Owner: backend queries/frontend loading. Dependencies: U6 and U7; workload decision D4 for larger changes. Size: M. Finding: F11.

- [x] Batch dataset-tag associations for list_datasets while preserving names/tag ordering and descendant semantics. Use SQL trace/query-count checks on representative synthetic catalogs.
- [x] Share existing root loader data with child features where ownership and mutation revalidation allow it. Compute sidebar counts once per input set and count a dataset once per subtree even when it has multiple descendant links.
- [x] Verify network behavior before adding caching. Avoid a hidden global cache with unclear invalidation.
- [x] Keep workload-dependent latency/memory budgets provisional because no target catalog size was supplied. Query-count regression proves the redundant SQL work is removed. Public list pagination, new indexes and chunked registration remain conditional on future workload evidence.

Files: catalog/repository.py, tags.py; web/app/root.tsx, shell.tsx, routes/datasets.tsx and dataset feature loader; focused tests; code map and performance notes in owning module docs.

Acceptance: list metadata uses a bounded number of SQL queries independent of dataset count; equivalent ordering/counts; no stale tag links/counts after mutation; row-only navigation avoids redundant requests. Set performance budgets from baseline and expected workload rather than inventing targets.

### U9. Align styling with frontend ownership

Owner: frontend design. Dependencies: U6. Size: S to M. Finding: F14.

- [x] Split existing style sections into tokens/base, shell, catalog and inspector ownership if visual review confirms lower change coupling. Preserve current CSS token names and document cascade/import order.
- [x] Keep responsive overrides beside the owning feature or in an explicit final override layer. Reuse existing accessible controls rather than building a general design-system framework.
- [x] Check keyboard focus, long values, panel collapse, narrow viewports, contrast and reduced motion. Fix demonstrated accessibility failures in bounded changes, not an unrequested redesign.

Files: web/app/app.css, root.tsx and proposed feature styles; docs/modules/workbench-design.md.

Acceptance: desktop and 1100px/768px breakpoint captures show intended layout; no accidental cross-feature cascade changes; all primary actions remain keyboard reachable; long content does not hide controls. Inspect screenshots at each specified breakpoint. No preexisting automated pixel baseline is available, so do not claim pixel equivalence.

### U10. Complete contributor and operations documentation

Owner: documentation with frontend/backend owners verifying their commands. Dependencies: start with U0, finish after relevant behavior units. Size: M. Findings: F7, F15.

- [x] Add a contributor how-to for locked setup, Python checks, frontend checks, synthetic test catalog, module ownership and a representative change workflow. Link it from current navigation and README without duplicating instructions.
- [x] Add backup/restore and recovery guidance for SQLite plus all referenced Parquet files. Use a consistent SQLite backup mechanism or a documented quiesced snapshot; copying only catalog.sqlite while WAL is active is insufficient.
- [x] Document seed ownership, supported concurrent writers, orphan diagnosis, lock contention, unsupported schema/corrupt snapshot symptoms, and safe rollback boundaries.
- [x] Put explicit persisted-data deletion and backup guidance immediately before docker compose down -v. Keep normal restart distinct from reset in the recipe.
- [x] Update code-map entry points/tests and API/config/record references with every unit. Preserve provenance meanings; record actual command verification separately from generated/edited timestamps.

Files: README.md, web/README.md, docs/index.md; new contributor and backup/recovery recipes under existing how-to/; existing architecture/modules/configuration/data references.

Acceptance: a contributor can find the owning module and run checks from docs; a new local checkout can reach an empty and seeded catalog; an isolated backup restores identical metadata, tags and example rows; no unexpected local-link breaks; OKF checks establish only the format properties actually tested.

## Sequence and review boundaries

Recommended order: U0 baseline/missing contract, then U1 frontend correctness and U2 trust boundary. Resolve D2 and deliver U3 publication safety before U7 lifecycle work. Resolve D3 before U4 identity work and finalize U5 contracts afterward. Then U6 feature ownership, U8 query/loading improvements and U9 styles. U10 starts immediately for missing guidance and finishes with a reproduction/restore walkthrough.

Implementation units remain separable in the working diff; no commits have been created. Each unit can be reviewed by its owning files. U0 may be split into documentation repair and test/CI foundation. U3 should be split into safe ownership, serialized publication and interruption tests when each intermediate state is safe. Do not mix mass formatting with correctness changes. Roll back behavior-preserving units by reverting code while retaining compatible data. Before identity/schema changes, create and test a catalog backup; document whether rollback needs old route support or a data migration. No migration should be described as reversible until a restore was exercised.

## Verification

Run these existing commands in a supported, provisioned development environment. They passed in WSL during implementation; actual output is captured in the local backend/frontend check files:

```bash
uv sync --locked
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run ty check
cd web
npm ci
npm run typecheck
npm run build
```

Add new frontend lint/format/test, browser-flow and documentation-check commands in U0 and record exact invocations in the contributor recipe. Use frozen/locked installs in CI. Tests must be deterministic and must not fetch Hugging Face data. Existing source tests can retain stubbed external clients; persistence/browser integration should use real local storage and HTTP boundaries.

- [x] Registration round-trip preserves message variants, JSON values, segment columns, ordering, provenance and counts: loaded = kept + dropped; zero kept rows remain rejected.
- [x] Real API tests prove identity, tag forest/path validation, pagination bounds, 404/422/internal errors and configured CORS behavior.
- [x] Publication interruption and two-process tests prove accepted ownership and retry semantics; restore proves the database and snapshots remain consistent.
- [x] Browser tests prove catalog browsing/filtering, detail direct links, back/forward, j/k across pages, raw view, attach/detach, empty/error states and optional browser capability failures.
- [x] Query counts and browser request traces prove U8 improvements without relying only on microbenchmarks.
- [x] Visual/keyboard checks cover breakpoints, long structured content, panel states, focus and reduced motion.
- [x] Documentation target links, selected frontmatter, setup commands and the backup/restore walkthrough pass in their claimed scope.

## Open questions and decision gates

Approval adopts the recommended local scope. D1 uses same-origin defaults with optional explicit development origins. D2 supports Linux local filesystems and process-death recovery, without claiming power-loss durability. D3 adds /dataset-ids/{id} while retaining existing name API routes and name workbench bookmarks. D4 keeps list responses and eager registration unchanged; bounded SQL query-count checks establish the known optimization. Larger workload-dependent designs remain outside this change.

| Gate | Question | Recommendation | Affected units |
| --- | --- | --- | --- |
| D1 | Is this strictly a local single-user tool, or must remote/multi-user access be supported? Which direct browser origins are supported? | Preserve local scope and same-origin proxy. Add explicit development origins only when required; remote access needs a separate authentication design. | U2 |
| D2 | Which platforms/filesystems and concurrent writer/startup patterns must be supported? What durability level is required after process death versus host/power loss? | Start with the current Linux/container local-filesystem deployment, explicitly serialize initialization, and preserve unrelated content. Confirm any Windows/network-filesystem requirement before choosing locking/publication primitives. | U3, U7, U10 |
| D3 | Must existing name-based API clients/bookmarks continue working, and are slash-containing display names intended? | Use existing UUIDs for transport identity while keeping display names; choose compatibility duration and route shape before migration. Restricting names is an alternative requiring an accepted-input policy. | U4, U5 |
| D4 | Expected catalog count, tag depth, row counts/payload size and concurrent readers/writers? | Measure bounded synthetic workloads first. Keep public list API and eager registration until size/resource evidence warrants another design. | U8, potential later streaming/pagination |

No estimates in calendar days are given because team capacity and these compatibility decisions are unknown. Relative unit sizes support sequencing without implying a delivery commitment.


## Implementation status

U0 through U10 are implemented. Final verification passed: 73 backend tests, nine frontend unit tests, six real-browser tests against the production SPA, Python and TypeScript checks, Ruff/Biome lint and formatting, production build, documentation file/frontmatter checks, and generated-contract drift checks. A clean npm ci succeeded. Disposable Compose verification passed empty-volume SPA/API proxying, five seeded dataset UUID/example round trips, and restart persistence of tag edits. The test containers and volume were removed. The GitHub workflow is configured; it has not been run remotely.

Implementation choices: seed snapshots live under .starter so volume mountpoints need not be replaced; relative metadata paths are rewritten before database publication. All initializers share the Linux kernel lock. Ordinary reads run no DDL. An ordinary initializer refuses to create an empty database over pending seed artifacts. Existing unversioned catalogs become schema version 1 without data conversion, while unsupported future versions fail before DDL. Backup uses SQLite backup plus immutable referenced snapshots and validates source and destination containment independently. Diagnostics never delete files. New frontend links use UUIDs, with legacy name lookup retained. Backend OpenAPI generates TypeScript declarations through a bounded checked generator, and runtime parsers retain validation ownership.

Independent correctness/security and code-quality reviews completed. Their actionable findings were fixed: backup destination traversal, pending seed recovery ownership, redundant renderer shape validation, and inaccurate Docker coverage documentation. The container smoke also exposed an inherited CRLF shebang failure, fixed by LF script normalization and a .gitattributes rule. Browser tests now use production preview to avoid changing Vite development-module caches after a clean install.

Evidence is local and gitignored under .audit/quality-refactor/: backend-checks.txt, frontend-checks.txt, docker-smoke.txt, decisions.jsonl and generated decisions.md. Screenshots at 1440, 1100 and 768 pixels were inspected and live in web/test-results/. No prior automated pixel baseline existed, so this is visual inspection rather than a pixel-equivalence claim. Checks did not establish full OKF conformance, remote CI success, or power-loss durability. Source changes are uncommitted.

Conditional streaming, public list pagination, remote authentication, Windows/network filesystem support and a general schema-migration framework are deliberately not introduced, consistent with the approved constraints. No production catalog or existing deployment was changed. The execution-evidence audit uses a different model family and is limited to local artifacts because the full transcript is unavailable to that reviewer.

## Attention

Execution-evidence reviewer: GPT-5.6 Sol. The final bounded recheck reported no remaining flags. Earlier flags on stale Docker/browser results, weak source-only evidence, omitted quality fixes and stale plan status were corrected through entries be72a830, 62e3c890, 59b89e78 and c0716a60 in the local append-only trail. The audit is limited to local artifacts and evidence locators because the full transcript was unavailable to that reviewer. The correctness reviewer also confirmed no outstanding findings after the pending-publication and backup-path fixes. A subsequent GPT-6 Luna handoff check confirmed the 73/9/6 counts and Docker evidence; its suggested baseline-table wording correction is applied above.

A final escalation-dependent recheck was not executed because automatic approval review hit an account usage limit. All implementation tests and smoke checks listed in Implementation status had already passed. Subsequent edits only clarify handoff wording and update documentation producer metadata.
