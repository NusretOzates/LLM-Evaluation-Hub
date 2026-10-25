---
type: Playbook
title: Run with Docker
description: Start the API and workbench with Compose. Demo data is copied only when requested.
tags: [operations]
generated: { by: human:nusret, at: 2026-10-25T22:32:00+03:00 }
status: stable
---

# Run with Docker

Use this when you want one command to start the catalog API and the workbench. The catalog lives on a volume that survives restarts. Demo rows stay unloaded unless you set `LLM_EVAL_SEED`. Field meanings are in [Runtime configuration](../configuration/runtime.md). Host processes without Docker are in [Run the API and workbench](run-locally.md).

## Steps

1. From the repository root, build and start both services:

```bash
docker compose up --build
```

2. Open `http://127.0.0.1:8080/datasets`.

The workbench proxies `/api` to the API service and strips that prefix. The API listens inside the Compose network. Port `8080` on the host is the workbench.

The first start creates an empty catalog when the volume has no `catalog.sqlite`. A later start keeps that volume, including tag edits. The workbench starts listening after the API answers `GET /datasets`.

3. Stop the containers when you are done:

```bash
docker compose down
```

`docker compose down` keeps the `catalog` volume. `docker compose restart` keeps it too.

## Load the demo catalog

The demo snapshot is about 70 KB. The API image stores it at `/opt/llm-eval/seed`. Set `LLM_EVAL_SEED` to that path and use a volume that has no `catalog.sqlite`:

```bash
docker compose down -v
LLM_EVAL_SEED=/opt/llm-eval/seed docker compose up --build
```

The copy publishes the database file last. A start that dies before that file exists tries the copy again. A start that finds `catalog.sqlite` keeps the volume, so `docker compose down -v` is what clears an existing catalog before a new copy.

The demo catalog has these datasets:

- `support-summaries`
- `intent-classification`
- `gsm8k-sample`
- `weather-tool-calls`
- `returns-faq-draft`

Leave `LLM_EVAL_SEED` unset, delete the volume, and start again to return to an empty catalog:

```bash
docker compose down -v
docker compose up --build
```

## Checks

- On a new volume, with `LLM_EVAL_SEED` unset, `curl -s http://127.0.0.1:8080/api/datasets` returns `[]`.
- On a new volume, with `LLM_EVAL_SEED=/opt/llm-eval/seed`, that request returns a JSON array that includes the five dataset names above.
- Create a tag in the workbench, run `docker compose restart`, and wait until `docker compose ps` shows the API as healthy. Reload `http://127.0.0.1:8080/datasets`. The new tag is still in the sidebar.
- `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/datasets` prints `200`.
