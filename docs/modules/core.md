---
type: Module
title: Core library
description: Dataset sources, the row processor, conversation records, and the local catalog.
tags: [core]
generated: { by: human:nusret, at: 2026-10-25T19:00:00+03:00 }
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

`process_rows` checks that `example.segments` has exactly the keys declared to `register`. Order of stored rows follows source order. Zero kept rows raise `EmptyDatasetError` and no snapshot is stored.

## Conversation record

`ProcessedExample` requires a non-empty `conversation`. When the first message is not `role: system`, `records.py:ensure_leading_system` inserts a system message with empty content. Segment names must match `[A-Za-z_][A-Za-z0-9_]*` and must not be `source_index`, `conversation`, `expected_output`, or `extras`.

`expected_output` is a JSON value or `None`. `None` is stored as a null column. The JSON text `null` is not used. `extras` is a JSON object for judge context. Message roles are `system`, `user`, `assistant`, and `tool`. The shapes and the empty-content rules are in [Stored snapshot](../data/snapshot.md).

## Repository

`DatasetRepository(root)` creates `root` and `catalog.sqlite` when they are missing. Methods that change or read the index:

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
