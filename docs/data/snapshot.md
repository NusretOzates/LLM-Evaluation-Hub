---
type: Reference
title: Stored snapshot
description: SQLite metadata, immutable Parquet rows, and conversation contracts.
generated: { by: process:codex-refactor, at: 2026-10-26T13:56:10+03:00 }
status: stable
---

# Stored snapshot

A catalog is a SQLite index plus immutable Parquet snapshots rooted at the directory passed to `DatasetRepository`. The database alone is not a complete backup. See [Backup and recover a catalog](../how-to/backup-and-recover.md).

## Identity and layout

`catalog.sqlite` stores dataset identities, source provenance, counts, tags and relative snapshot paths. A dataset has an immutable UUID `id` and a unique, case-sensitive `name`. Names are display/registration identities and may contain Unicode, `/`, `%`, `?`, or `#`. HTTP and workbench links use UUIDs.

New registrations write `datasets/<uuid>/rows.parquet`. Starter publication stores snapshots below `.starter/` and rewrites relative paths in its consistent SQLite backup. Consumers must use `parquet_path`, not assume every snapshot starts with `datasets/`. The HTTP metadata omits this storage path. `.catalog.lock` coordinates initialization. Keep it in place while the catalog is in use.

## Snapshot formats

Catalog metadata records snapshot format 2, the only supported format. Every row contains a JSON-encoded `tools` column for its available function definitions. Other format versions are rejected. Missing or malformed tool data is corruption.

## Row schema

| Column | Storage type | Meaning |
| --- | --- | --- |
| `source_index` | Int64 | Zero-based index in the source frame read for this registration. Dropped rows leave gaps. |
| `conversation` | UTF-8 string | JSON array of normalized message objects. |
| `expected_output` | Nullable UTF-8 string | Serialized JSON value. Python `None` is a null column, not the string `null`. Empty string output is serialized as `""`. |
| `extras` | UTF-8 string | JSON object containing additional context. Empty context is `{}`. |
| `tools` | UTF-8 string | JSON array of available function definitions for this row. Empty list is `[]`. |
| Each declared segment | UTF-8 string | Required string value for that segment. Empty values are allowed. |

Rows preserve source order. `examples(offset, limit)` offsets count retained rows, not `source_index`. The workbench displays retained rows starting at 1. The API offset starts at 0. The example API defaults to 20 rows and allows 1 through 100. The workbench requests 50.

## Conversation messages

A conversation is nonempty. Messages are preserved without adding a system message. Unknown message fields are rejected by the backend.

| Role | Fields and invariants |
| --- | --- |
| `system` | String `content`, including the empty string. |
| `user` | String `content` or a nonempty array of content parts. A string may be empty. |
| `assistant` | Optional nullable string `content` and `thinking`, plus function `tool_calls`. At least one of non-null content, non-null thinking, or a nonempty call list is required. Empty strings count as present. |
| `tool` | String `content`, nonempty `tool_call_id`, optional nullable string `name`. |

A text part has `type: text` and string `text`. Media parts have `type: image`, `video`, or `audio` and exactly one nonempty `url` or `path`. The workbench renders a media-type placeholder; it does not fetch referenced media.

Available tool definitions are separate from conversation tool calls. A definition has `type: function` and a `function` object with a nonempty `name`, a JSON-object `parameters`, optional `description`, and optional `strict`. Definitions are per-row and are not executed. The complete JSON Schema dialect is not validated.

A tool call has nonempty `id`, `type: function`, and a function containing nonempty `name` and JSON-object `arguments`. Registration accepts OpenAI-style JSON-string arguments and normalizes them to an object. This schema does not prove that a tool result refers to a previously declared call.

`expected_output`, extras and function arguments permit JSON strings, booleans, finite numbers, arrays, objects and null as appropriate. Non-finite numbers and non-JSON objects are rejected. No evaluator, label-validation process, metric or judge is run by this repository.

## Segments and counts

Segment keys match `[A-Za-z_][A-Za-z0-9_]*` and exclude `source_index`, `conversation`, `expected_output`, `extras` and `tools`. The processor must return exactly the keys declared to registration, in any mapping order. Storage preserves declaration order. No missing-key filling or implicit segment coercion is performed by processing.

`rows_loaded` is the source frame height after the requested prefix limit. `rows_dropped` counts processor returns of `None`. `rows_kept` counts successful retained examples. The invariant is `rows_loaded = rows_kept + rows_dropped`. Exceptions and malformed examples fail registration rather than count as dropped rows. Zero retained rows fail registration and do not publish a snapshot.

## Tags and provenance

Tags are tree nodes addressed by `/`-joined paths. A segment cannot be empty or contain `/`. Dataset links are direct links; querying a parent also matches datasets linked below it. Counts count a dataset once per subtree even when it has multiple descendant links. `__proto__`, `constructor` and `toString` remain legal names.

The record stores processor identity, source type, requested coordinates/revision, resolved Hub SHA, requested limit and UTC creation time. Credentials are excluded from descriptors and persisted records. The processor ID is caller-supplied provenance, not an automatic source-code hash. A resolved source SHA does not establish processor reproducibility by itself.
