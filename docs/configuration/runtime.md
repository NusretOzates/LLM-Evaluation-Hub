---
type: Reference
title: Runtime configuration
description: Environment variables and proxies that select the catalog, the starter snapshot, and the Hub token.
tags: [configuration]
generated: { by: human:nusret, at: 2026-10-25T22:32:00+03:00 }
status: stable
---

# Runtime configuration

There is no config file. These values are read at process start or when a source is constructed.

| Name | Who reads it | Default | Effect |
| --- | --- | --- | --- |
| `LLM_EVAL_CATALOG` | `llm_evaluation_hub.api.asgi:app` | `data/catalog` | Directory passed to `DatasetRepository`. Relative paths are relative to the process working directory. |
| `LLM_EVAL_SEED` | `llm_evaluation_hub.api.asgi:app` | unset | Directory copied into `LLM_EVAL_CATALOG` when `catalog.sqlite` is absent. Empty is the same as unset. |
| `HF_TOKEN` | `HfDatasetSource` when `token` is omitted | unset | Hub credential for `dataset_info` and `load_dataset`. Not stored in SQLite or Parquet. |
| Vite proxy `/api` | `web/vite.config.ts` | target `http://127.0.0.1:8000` | Dev and preview strip the `/api` prefix and forward the rest. |
| `API_UPSTREAM` | workbench image `web/nginx.conf.template` | `http://api:8000` | Docker proxy target for `/api`. The prefix is stripped. |

A registration script does not read `LLM_EVAL_CATALOG`. Pass the same directory to `DatasetRepository` that the API uses, or the workbench will show a different catalog.

`LLM_EVAL_SEED` is published by `ensure_starter_catalog`. The copy runs only when the target has no `catalog.sqlite`. An interrupted copy stops before that file exists, and the next start replaces it. A target that already has `catalog.sqlite` is kept, including Parquet files and later tag edits. Compose mounts a named volume at `LLM_EVAL_CATALOG` and forwards `LLM_EVAL_SEED` when the shell sets it. The API image keeps the demo snapshot at `/opt/llm-eval/seed` and does not copy it on its own. The commands are in [Run with Docker](../how-to/run-with-docker.md).

`HfDatasetSource(..., token=...)` overrides `HF_TOKEN` for that object. An empty constructor token is still an explicit token. Only `token=None`, the default, falls through to the environment.

The API binds whatever host and port you pass to uvicorn. The documented local command uses uvicorn's default `127.0.0.1:8000`, which matches the Vite proxy. Changing the API port requires the same change in `web/vite.config.ts`.

CORS is `*` inside `create_app`. It is not an environment variable.
