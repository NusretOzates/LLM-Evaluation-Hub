---
type: Reference
title: Catalog API
description: HTTP operations for tags, dataset metadata, and pages of stored rows.
tags: [api]
generated: { by: process:codex-refactor, at: 2026-10-26T13:56:10+03:00 }
status: stable
---

# Catalog API

`create_app(catalog_root)` in `src/llm_evaluation_hub/api/app.py:create_app` serves one `DatasetRepository`. The uvicorn factory `llm_evaluation_hub.api.asgi:app` passes `LLM_EVAL_CATALOG` or `data/catalog`. When `LLM_EVAL_SEED` is set, the factory publishes that directory into the catalog root before serving. [Runtime configuration](../configuration/runtime.md) states when the copy runs. Responses are JSON. CORS grants no cross-origin access by default. Explicit development origins are optional. There is no authentication.

The catalog routes do not register datasets or return `parquet_path`. The separate import routes accept bounded source and processor requests and submit durable jobs.

## Operations

`GET /health` returns `{"status":"ok"}` without reading SQLite or Parquet. Docker uses it to check API process responsiveness.

| Method and path | Body | Success | Result |
| --- | --- | --- | --- |
| `GET /tags` | none | 200 | Tag forest |
| `POST /tags` | Tag forest | 201 when any node is new, otherwise 200 | Same forest with `path` filled |
| `GET /datasets` | none | 200 | Dataset array. Optional `tag` query includes descendants. |
| `GET /dataset-ids/{id}` | none | 200 | One dataset |
| `POST /dataset-ids/{id}/tags` | `{ "paths": ["A/B"] }` | 200 | Dataset after linking existing tags |
| `DELETE /dataset-ids/{id}/tags` | `{ "paths": ["A/B"] }` | 200 | Dataset after unlinking |
| `GET /dataset-ids/{id}/examples` | none | 200 | Page of stored rows |

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
| 422 | Request-domain validation, including a bad tag forest, a bad offset, or a bad limit. FastAPI validation errors use the same status with a list `detail`. |

`DuplicateDatasetError` is not produced by these routes, because registration is not an HTTP operation.

## Immutable identity and trust boundary

Dataset detail, example and tag endpoints accept immutable UUIDs through `/dataset-ids/{id}`. Names are display labels and Python registration identities, not HTTP lookup keys. Missing IDs return 404. Workbench links use UUIDs.

The default browser interface is same-origin through `/api`. CORS is disabled unless `LLM_EVAL_ORIGINS` names explicit supported origins. This is a local, unauthenticated service. An origin allowlist is not authentication for nonbrowser clients and does not authorize remote exposure. Request-domain validation maps to 422. Stored-data/SQLite/filesystem failures map to a generic 500 without returning payload details. The OpenAPI schema is the source for `web/app/api-schema.ts`; runtime response parsing remains in the frontend HTTP boundary.

## Dataset imports

The import router in `src/llm_evaluation_hub/api/import_routes.py` exposes `GET /dataset-sources`, `POST /dataset-source-samples`, `POST /dataset-previews`, `POST /dataset-imports`, `GET /dataset-imports`, `GET /dataset-imports/{job_id}`, `POST /dataset-imports/{job_id}/cancel`, and `GET /dataset-ids/{dataset_id}/processor`. Submission returns `202`. The request and response models live in `src/llm_evaluation_hub/imports/contracts.py`; import-specific request validation omits submitted payload values from error responses.

Source and preview operations return pinned coordinates and safe row diagnostics. A successful preview produces an expiring attestation bound to the source SHA, row limit, processor hash, segment keys, contract version, and runtime policy. Submission copies the full execution specification into a durable job. Job states are `queued`, `running`, `cancelling`, `succeeded`, `failed`, `cancelled`, and `interrupted`. The supervisor serializes cancellation with publication; only a completed job publishes a snapshot. See [Import a dataset in the workbench](../how-to/import-a-dataset.md) for the user workflow and [Core library](core.md) for execution limits.


Inference profiles, dataset output metadata, request preview and tests, runs, results, cancellation and resume are described in [Inference runs](inference.md). The routes and typed request/response models are in `api/inference_routes.py` and `inference/contracts.py`.
