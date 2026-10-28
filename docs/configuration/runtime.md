---
type: Reference
title: Runtime configuration
description: Environment variables and proxies that select the catalog, the starter snapshot, and the Hub token.
tags: [configuration]
generated: { by: process:codex-refactor, at: 2026-10-26T13:56:10+03:00 }
status: stable
---

# Runtime configuration

There is no config file. These values are read at process start or when a source is constructed.

| Name | Who reads it | Default | Effect |
| --- | --- | --- | --- |
| `LLM_EVAL_CATALOG` | `llm_evaluation_hub.api.asgi:app` | `data/catalog` | Directory passed to `DatasetRepository`. Relative paths are relative to the process working directory. |
| `LLM_EVAL_SEED` | `llm_evaluation_hub.api.asgi:app` | unset | Directory copied into `LLM_EVAL_CATALOG` when `catalog.sqlite` is absent. Empty is the same as unset. |
| `LLM_EVAL_ORIGINS` | `llm_evaluation_hub.api.asgi:app` | unset | Explicit comma-separated HTTP origins for optional direct browser access. |
| `HF_TOKEN` | `HfDatasetSource` when `token` is omitted; import Hugging Face adapter | unset | Backend Hub credential for source resolution and loading. Not stored in SQLite, Parquet, form state, or job specifications. Compose passes the variable to the API container. |
| Vite proxy `/api` | `web/vite.config.ts` | target `http://127.0.0.1:8000` | Dev and preview strip the `/api` prefix and forward the rest. |
| `API_UPSTREAM` | workbench image `web/nginx.conf.template` | `http://api:8000` | Docker proxy target for `/api`. The prefix is stripped. |
| `LLM_EVAL_WEB_PORT` | Docker Compose | `8080` | Host port for the workbench, bound to `127.0.0.1`. Set a free port when `8080` is occupied. |

A registration script does not read `LLM_EVAL_CATALOG`. Pass the same directory to `DatasetRepository` that the API uses, or the workbench will show a different catalog.

`LLM_EVAL_SEED` is published by `ensure_starter_catalog` under the same startup lock as repository initialization. Existing databases win. A target with unrelated content and no database is rejected. Seed and target paths cannot overlap. A private staging directory receives a consistent SQLite backup and snapshots. The completed payload is renamed to `.starter`, relative database snapshot paths are prefixed with `.starter/`, and the database is published last. A completed publication can resume after process death; incomplete stages are preserved for inspection. See [Backup and recover](../how-to/backup-and-recover.md). Compose forwards the seed path and ships `/opt/llm-eval/seed` as an optional source.

`HfDatasetSource(..., token=...)` overrides `HF_TOKEN` for that object. An empty constructor token is still an explicit token. Only `token=None`, the default, falls through to the environment.

The API binds whatever host and port you pass to uvicorn. The documented local command uses uvicorn's default `127.0.0.1:8000`, which matches the Vite proxy. Changing the API port requires the same change in `web/vite.config.ts`.

`LLM_EVAL_ORIGINS` defaults to unset (no cross-origin browser grant). Set a comma-separated list of exact HTTP origins, such as `http://127.0.0.1:5173`, only for direct cross-origin development. Wildcards, paths, credentials, queries and fragments are rejected. The same-origin Vite/nginx proxies need no CORS grant. `create_app(root, allowed_origins=(... ,))` also accepts an explicit tuple for embedding.
