---
type: Reference
title: Runtime configuration
description: Environment variables and the development proxy that select the catalog and the Hub token.
tags: [configuration]
generated: { by: human:nusret, at: 2026-10-25T19:00:00+03:00 }
status: stable
---

# Runtime configuration

There is no config file. These values are read at process start or when a source is constructed.

| Name | Who reads it | Default | Effect |
| --- | --- | --- | --- |
| `LLM_EVAL_CATALOG` | `llm_evaluation_hub.api.asgi:app` | `data/catalog` | Directory passed to `DatasetRepository`. Relative paths are relative to the process working directory. |
| `HF_TOKEN` | `HfDatasetSource` when `token` is omitted | unset | Hub credential for `dataset_info` and `load_dataset`. Not stored in SQLite or Parquet. |
| Vite proxy `/api` | `web/vite.config.ts` | target `http://127.0.0.1:8000` | Dev and preview strip the `/api` prefix and forward the rest. |

A registration script does not read `LLM_EVAL_CATALOG`. Pass the same directory to `DatasetRepository` that the API uses, or the workbench will show a different catalog.

`HfDatasetSource(..., token=...)` overrides `HF_TOKEN` for that object. An empty constructor token is still an explicit token. Only `token=None`, the default, falls through to the environment.

The API binds whatever host and port you pass to uvicorn. The documented local command uses uvicorn's default `127.0.0.1:8000`, which matches the Vite proxy. Changing the API port requires the same change in `web/vite.config.ts`.

CORS is `*` inside `create_app`. It is not an environment variable.
