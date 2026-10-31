---
type: Module
title: Core library
description: Dataset sources, the row processor, conversation records, and the local catalog.
tags: [core]
generated: { by: process:codex-refactor, at: 2026-10-26T13:56:10+03:00 }
status: stable
---

# Core library

`llm_evaluation_hub.core.datasets` turns a table into stored conversation rows and indexes them. Callers that register datasets import `DatasetRepository`, `HfDatasetSource`, and `ProcessedExample` from that package. The HTTP layer uses the same repository. It does not own a second store.

## Source

A source implements `DatasetSource` in `src/llm_evaluation_hub/core/datasets/sources/protocol.py:DatasetSource`.

| Method | Result |
| --- | --- |
| `read(limit=None)` | Polars frame. `limit` is a positive prefix. |
| `describe()` | `SourceDescriptor` after the read that produced the snapshot. |

`describe` has no token or credential field. `HfDatasetSource` sets `source_type` to `hf_dataset`. It resolves the dataset commit with `HfApi.dataset_info`, then loads that SHA through `datasets.load_dataset`. A `limit` rewrites a plain split name to `split[:limit]`. A split string that already contains `[` is rejected when `limit` is set. The token comes from the constructor when passed, otherwise from `HF_TOKEN`. Neither value is written to the catalog.

## Processor

`RowProcessor` in `src/llm_evaluation_hub/core/datasets/processing.py:RowProcessor` is a function from one source row dict to `ProcessedExample` or `None`. `None` drops that source row. Any other return type raises `RowProcessingError` and stops registration. An exception from the processor does the same, and the error names the zero-based source index.

`process_rows` checks that `example.segments` has exactly the keys declared to `register`. Order of stored rows follows source order. Python `DatasetRepository.register` raises `EmptyDatasetError` when no rows are kept. The import job applies the same nonempty-publication rule after processing.

## Conversation record

`ProcessedExample` requires a non-empty `conversation`. Available tool definitions are an optional per-example list, defaulting to `[]`. Each definition uses the canonical function envelope with a nonempty name and JSON-object `parameters`. Definitions are validated as bounded JSON data; the full JSON Schema dialect and arguments are not validated, and definitions are never executed. Conversations are preserved without inserting a system message. Segment names must match `[A-Za-z_][A-Za-z0-9_]*` and must not be `source_index`, `conversation`, `expected_output`, or `extras`.

`expected_output` is a JSON value or `None`. `None` is stored as a null column. The JSON text `null` is not used. `extras` is a JSON object for judge context. Message roles are `system`, `user`, `assistant`, and `tool`. The shapes and the empty-content rules are in [Stored snapshot](../data/snapshot.md).

## Repository

`DatasetRepository(root)` creates `root` and `catalog.sqlite` when they are missing. Initialization uses a shared startup lock and configures WAL and schema version 1. Existing unversioned catalogs are initialized in place. Ordinary connections set foreign keys and a 5 second busy timeout without running schema DDL. Unknown future schema versions are rejected. After a process is killed, SQLite recovers committed database writes on reopening. This does not establish atomicity across SQLite and snapshot files. Methods that change or read the index:

| Method | Effect |
| --- | --- |
| `create_tag(name, parent=None)` | Insert one node. Does not link a dataset. |
| `delete_tag(path)` | Delete a node with no children and no dataset links. |
| `ensure_path` / `ensure_paths` | Create missing nodes along paths. Return whether any node was new. |
| `register(...)` | Read, process, write Parquet, insert the dataset. |
| `add_tags` / `remove_tags` | Link or unlink existing tag paths. Nodes stay in the tree. |
| `get` / `list_datasets(tag=None)` | Metadata. A tag argument includes descendant links. |
| `rows` | Full Polars snapshot. |
| `examples(name, offset=0, limit=None)` | Parsed `ProcessedExample` page. `offset` is at least 0. `limit` is at least 1 when set. |

`register` fails before the source read when the dataset name exists, `processor_id` or the name is empty, `limit` is below 1, or a tag path is missing. Dataset names and tag paths are matched as stored. Tag names cannot be empty or contain `/`.

Catalog errors are `DuplicateDatasetError`, `UnknownDatasetError`, `DuplicateTagError`, `UnknownTagError`, and `TagInUseError` in `src/llm_evaluation_hub/core/datasets/catalog/errors.py`. They subclass `CatalogError`.

`get_by_id` resolves an immutable UUID without changing the name-based Python API. `inspect_storage` reports missing and unreferenced Parquet files without deleting them. List metadata batches tag associations into a second query instead of querying per dataset. See [Backup and recover](../how-to/backup-and-recover.md) for the concurrency, durability and recovery contract.

## Workbench imports

The local API exposes a bounded Hugging Face import service in `src/llm_evaluation_hub/imports/`. `sources.py` resolves a Hub revision and streams up to 10,000 JSON rows. `previews.py` caches source samples and issues short-lived preview attestations. `runtime.py` runs each row in a fresh constrained Monty session and validates its output with `ProcessedExample`. `jobs.py` supervises durable jobs, cancellation, recovery, and parent-only publication. `api/import_routes.py` exposes the import endpoints; `app.py` starts and stops the supervisor through the application lifespan.

The import processor accepts a dictionary or `None`. It has no external modules, filesystem, network, or host callbacks. Limits are server controlled: source rows 10,000; preview rows 10; source code 64 KiB; row input/output 1 MiB each; aggregate import input/output 128 MiB each; Monty allocation 64 MiB; row time 250 ms; operation deadline 30 seconds; and import deadline 10 minutes. Queued imports are capped at 20. A sample with no retained rows may preview successfully, but publication requires at least one retained row. Import errors fail the whole import without a partial snapshot. Interrupted jobs require a manual retry and are not resumed automatically. See [Import a dataset in the workbench](../how-to/import-a-dataset.md) for the user flow and [Backup and recover](../how-to/backup-and-recover.md) for catalog recovery.

Dataset deletion moves catalog records to Trash while preserving snapshots and tag links. Names are reserved until permanent deletion, so restoring cannot overwrite another dataset. Permanent deletion is retryable: a pending marker prevents restoration before the catalog removes the owned `datasets/<id>/rows.parquet` snapshot and metadata. Import history remains, with its dataset link cleared after deletion. Tag deletion removes labels and associations only; it can instead promote direct children, rejecting path collisions atomically. Tag deletion has no undo.
