---
type: Playbook
title: Run the API and workbench
description: Install dependencies, start the catalog API, and open the workbench against that catalog.
tags: [operations]
generated: { by: human:nusret, at: 2026-10-25T19:00:00+03:00 }
status: stable
---

# Run the API and workbench

Use this when you want to browse a catalog that is already on disk. To put a dataset into that catalog, follow [Register a dataset](register-a-dataset.md) first. Field meanings are in [Runtime configuration](../configuration/runtime.md).

## Steps

1. From the repository root, install Python dependencies:

```bash
uv sync
```

2. Start the API against the catalog directory you will browse:

```bash
LLM_EVAL_CATALOG=data/catalog uv run uvicorn llm_evaluation_hub.api.asgi:app --factory
```

The process listens on `127.0.0.1:8000`. `GET http://127.0.0.1:8000/datasets` returns a JSON array. An empty catalog returns `[]`.

3. In another shell, install and start the workbench:

```bash
cd web && npm install && npm run dev -- --host 127.0.0.1 --port 5173
```

4. Open `http://127.0.0.1:5173/datasets`. The page lists datasets from `data/catalog`. A tag in the sidebar filters that list. Opening a dataset shows its first stored row.

## Checks

- `uv run pytest` runs the Python tests.
- `cd web && npm run typecheck` checks the workbench.
- If the workbench says the catalog API is not reachable, the API is not listening on port 8000, or the Vite proxy target was changed.

The workbench does not create the catalog directory. The API does, on startup, when `LLM_EVAL_CATALOG` is missing on disk.
