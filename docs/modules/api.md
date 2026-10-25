---
type: Reference
title: Catalog API
description: HTTP operations for tags, dataset metadata, and pages of stored rows.
tags: [api]
generated: { by: human:nusret, at: 2026-10-25T19:00:00+03:00 }
status: stable
---

# Catalog API

`create_app(catalog_root)` in `src/llm_evaluation_hub/api/app.py:create_app` serves one `DatasetRepository`. The uvicorn factory `llm_evaluation_hub.api.asgi:app` passes `LLM_EVAL_CATALOG` or `data/catalog`. Responses are JSON. CORS allows every origin, method, and header. There is no authentication.

The API does not register datasets and does not return `parquet_path`. Snapshot writes stay on `DatasetRepository.register`.

## Operations

| Method and path | Body | Success | Result |
| --- | --- | --- | --- |
| `GET /tags` | none | 200 | Tag forest |
| `POST /tags` | Tag forest | 201 when any node is new, otherwise 200 | Same forest with `path` filled |
| `GET /datasets` | none | 200 | Dataset array. Optional `tag` query includes descendants. |
| `GET /datasets/{name}` | none | 200 | One dataset |
| `POST /datasets/{name}/tags` | `{ "paths": ["A/B"] }` | 200 | Dataset after linking existing tags |
| `DELETE /datasets/{name}/tags` | `{ "paths": ["A/B"] }` | 200 | Dataset after unlinking |
| `GET /datasets/{name}/examples` | none | 200 | Page of stored rows |

`paths` must contain at least one string. Example `offset` defaults to 0 and must be at least 0. Example `limit` defaults to 20 and must be from 1 through 100. `total` is `rows_kept` for that dataset, not the number of rows in the page.

## Tag forest

`GET /tags` and `POST /tags` use the same nested object. Keys are tag names. Each node has `children`. Responses add `path`. A post creates missing nodes, including parents of a leaf. An empty body, an empty name, a name containing `/`, a duplicate name in one object, or a `path` that disagrees with the nesting is rejected.

```json
{
  "Trendyol Cases": {
    "children": {
      "Summarization": { "children": {} }
    }
  }
}
```

The stored path for that leaf is `Trendyol Cases/Summarization`.

## Dataset object

| Field | Meaning |
| --- | --- |
| `id` | UUID stored in SQLite |
| `name` | Unique dataset name |
| `created_at` | UTC timestamp of the insert |
| `processor_id` | Caller-supplied processor name |
| `source_type` | `hf_dataset` for `HfDatasetSource` |
| `repo_id`, `config`, `split`, `revision`, `resolved_sha` | Source provenance. Null when the source has no such field. |
| `row_limit` | Prefix requested at registration, or null |
| `rows_loaded`, `rows_kept`, `rows_dropped` | Counts from processing. See [Stored snapshot](../data/snapshot.md). |
| `segment_keys` | Segment column names, in declaration order |
| `tags` | Paths linked directly to this dataset |

## Errors

| Status | When |
| --- | --- |
| 404 | `UnknownDatasetError` or `UnknownTagError`. The body is `{ "detail": "<message>" }`. |
| 422 | `ValueError` from validation, including a bad tag forest, a bad offset, or a bad limit. FastAPI validation errors use the same status with a list `detail`. |

`DuplicateDatasetError` is not produced by these routes, because registration is not an HTTP operation.
