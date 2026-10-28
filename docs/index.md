---
okf_version: "0.2"
---

# LLM Evaluation Hub documentation

This bundle documents the local dataset catalog, the HTTP API, and the workbench. Register datasets with the Python library or import them from the workbench. The repository does not run evaluations, train models, or serve model inference.

| Directory | Role |
| --- | --- |
| `project/` | What this slice is for, and what it leaves out |
| `architecture/` | Boundaries, registration flow, and where to change code |
| `modules/` | Core library, HTTP API, workbench behavior, and workbench design |
| `data/` | Stored snapshot and conversation record |
| `configuration/` | Catalog path, Hub token, and the dev proxy |
| `how-to/` | Run the stack and register a dataset |
| `glossary.md` | Names used across those documents |

## Understand the system

- [Purpose and scope](project/purpose.md) states who uses the catalog and which jobs are out of scope.
- [Architecture](architecture/overview.md) shows how a source becomes a snapshot and how the workbench reads it.
- [Stored snapshot](data/snapshot.md) defines a row, a tag, and the count fields.

## Change the code

- [Code map](architecture/code-map.md) lists each capability, its entry point, the files that implement it, and the tests that cover it.
- [Core library](modules/core.md), [Catalog API](modules/api.md), and [Workbench](modules/workbench.md) are the behavior references.
- [Workbench design](modules/workbench-design.md) is the visual system: tokens, layout, type, and the rules for changing them.

## Run it

- [Run the API and workbench](how-to/run-locally.md) starts both processes on the host.
- [Run with Docker](how-to/run-with-docker.md) starts them in Compose. The catalog volume survives restarts, and demo data is copied only when `LLM_EVAL_SEED` is set.
- [Import a dataset in the workbench](how-to/import-a-dataset.md) samples a Hugging Face source, previews a processor, and submits a durable import.
- [Register a dataset](how-to/register-a-dataset.md) writes a snapshot from Python.
- [Runtime configuration](configuration/runtime.md) lists `LLM_EVAL_CATALOG`, `LLM_EVAL_SEED`, `HF_TOKEN`, and the `/api` proxies.

## Contribute and recover

- [Develop and test](how-to/develop-and-test.md) gives locked setup, quality commands, synthetic browser tests and transport generation.
- [Back up and recover](how-to/backup-and-recover.md) preserves metadata and snapshots and explains concurrency, failed publication and restore checks.
