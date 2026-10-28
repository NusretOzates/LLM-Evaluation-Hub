---
type: Reference
title: Code map
description: Where to change catalog registration, HTTP reads, the workbench, and the Docker stack.
tags: [architecture]
generated: { by: process:codex-refactor, at: 2026-10-26T13:56:10+03:00 }
status: stable
---

# Code map

Start here when a behavior change needs a file. Each row is one capability. Paths are relative to the repository root.

| Capability | Entry point | Key files | Tests |
| --- | --- | --- | --- |
| Register a snapshot from Python | `llm_evaluation_hub.core.datasets:DatasetRepository.register` | `src/llm_evaluation_hub/core/datasets/catalog/repository.py:DatasetRepository.register`, `src/llm_evaluation_hub/core/datasets/processing.py:process_rows` | `tests/datasets/catalog/test_repository.py`, `tests/datasets/test_processing.py` |
| Tag tree and dataset links | `DatasetRepository.create_tag`, `add_tags`, `remove_tags`, `delete_tag` | `src/llm_evaluation_hub/core/datasets/catalog/tags.py:TagStore`, `repository.py:DatasetRepository` | `tests/datasets/catalog/test_tags.py` |
| Conversation record | `llm_evaluation_hub.core.datasets:ProcessedExample` | `src/llm_evaluation_hub/core/datasets/records.py:ProcessedExample` | `tests/datasets/test_records.py` |
| Hugging Face source | `llm_evaluation_hub.core.datasets:HfDatasetSource` | `src/llm_evaluation_hub/core/datasets/sources/hf.py:HfDatasetSource` | `tests/datasets/sources/test_hf.py` |
| Dataset import API | `llm_evaluation_hub.api.import_routes:router` | `src/llm_evaluation_hub/api/import_routes.py`, `src/llm_evaluation_hub/imports/contracts.py` | `tests/imports/` and `tests/api/test_import_routes.py` |
| Import source, preview, runtime, and jobs | `llm_evaluation_hub.imports` | `src/llm_evaluation_hub/imports/sources.py`, `previews.py`, `runtime.py`, `jobs.py`, `worker.py` | `tests/imports/` |
| Catalog HTTP API | `llm_evaluation_hub.api:create_app` | `src/llm_evaluation_hub/api/app.py:create_app`, `src/llm_evaluation_hub/api/routes.py`, `src/llm_evaluation_hub/api/schemas.py` | `tests/api/test_dataset_routes.py`, `tests/api/test_tag_routes.py` |
| API process | `llm_evaluation_hub.api.asgi:app` | `src/llm_evaluation_hub/api/asgi.py:app` | `tests/api/` |
| Starter catalog | `llm_evaluation_hub.api.seed:ensure_starter_catalog` | `src/llm_evaluation_hub/api/seed.py:ensure_starter_catalog`, `src/llm_evaluation_hub/api/asgi.py:app` | `tests/api/test_seed.py` |
| Docker stack | `compose.yaml` | `Dockerfile`, `web/Dockerfile`, `web/docker-entrypoint.sh`, `web/nginx.conf.template`, `docker/seed/` | Manual Compose empty/seed/restart smoke; see [Docker recipe](../how-to/run-with-docker.md) |
| Dataset import workbench | routes `/dataset-imports/new`, `/dataset-imports`, `/dataset-imports/:id` | `web/app/features/dataset-imports/`, `web/app/api-schema.ts` | `web/tests/`, `web/e2e/` |
| Workbench shell and tags | route `/datasets` | `web/app/shell.tsx:Shell`, `web/app/routes/datasets.tsx`, `web/app/catalog.ts` | `web/e2e/catalog.spec.ts` |
| Row inspector | route `/datasets/:name` | `web/app/routes/dataset.tsx:DatasetPage`, `web/app/features/dataset-inspector/` | `web/e2e/catalog.spec.ts` |
| Workbench visual design | `web/app/app.css` | `web/app/styles/`, `web/app/root.tsx` font imports | `web/e2e/catalog.spec.ts` |

Public Python imports for registration are `DatasetRepository`, `HfDatasetSource`, `DatasetSource`, and `ProcessedExample` from `llm_evaluation_hub.core.datasets`. Catalog errors are exported from `llm_evaluation_hub.core.datasets.catalog`, not from that package root. `create_app` is the public API constructor. The uvicorn factory is `llm_evaluation_hub.api.asgi:app`.

The workbench has unit tests in `web/tests/` and real API/browser tests in `web/e2e/`. Full commands are in [Develop and test](../how-to/develop-and-test.md). API and core behavior are covered by `uv run pytest`.

| Additional concern | Entry point | Key files | Tests |
| --- | --- | --- | --- |
| Startup ownership | `catalog_lock` | `src/llm_evaluation_hub/core/datasets/catalog/storage.py` | `tests/api/test_seed.py` |
| Transport types | `scripts/export_contract.py` | `web/app/api-schema.ts`, `catalog-types.ts`, `catalog-parsers.ts` | `web/tests/catalog.test.ts`, contract CI check |
| Backup/restore | `scripts/catalog_backup.py` | `DatasetRepository.inspect_storage` | `tests/datasets/catalog/test_repository.py` |
| Documentation checks | `scripts/check_docs.py` | `docs/` concepts and links | quality workflow |
