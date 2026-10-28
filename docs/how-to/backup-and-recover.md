---
type: Playbook
title: Back up and recover a catalog
description: Preserve SQLite metadata and referenced immutable snapshots, diagnose interrupted work and restore.
generated: { by: process:codex-refactor, at: 2026-10-26T13:56:10+03:00 }
status: stable
---

# Back up and recover a catalog

Use this before resetting a volume, changing storage contracts, or investigating corruption. A backup contains a consistent SQLite backup and every snapshot referenced by that backup. Copying `catalog.sqlite` alone while WAL is active can omit committed metadata. The catalog's process-restart guarantee is not a power-loss or replicated-storage guarantee.

## Back up a host catalog

Stop external scripts that modify or delete snapshot files. Normal registration adds immutable files, and API tag edits are captured at the SQLite backup's consistent point in time. The backup command never overwrites an existing destination:

```bash
uv run python scripts/catalog_backup.py data/catalog data/backups/catalog-before-refactor
```

The destination must be a new directory outside the source tree. The command uses SQLite's backup API, checks database integrity, copies referenced snapshots and publishes the completed backup by directory rename. Failure before publication leaves no completed destination. Preserve a failed process's `.catalog-backup-*` directory for inspection before removing it manually.

## Restore and verify

Stop every API and registration process using the target. Keep the original catalog intact. Restore into a new sibling directory:

```bash
uv run python scripts/catalog_backup.py data/backups/catalog-before-refactor data/restored-catalog
LLM_EVAL_CATALOG=data/restored-catalog uv run uvicorn llm_evaluation_hub.api.asgi:app --factory
curl -f http://127.0.0.1:8000/datasets
```

Compare dataset IDs, names, counts, tag links and sample rows with the backup's expected contents. Set the workbench/API to the restored root only after these checks. `DatasetRepository(Path("data/restored-catalog")).inspect_storage()` must report empty `missing` and `unreferenced` lists for a clean backup. Automated tests exercise a complete backup and restore with exact record/example equality.

For Docker, stop the stack and use a stopped-volume backup approved for your Docker host, including all volume contents, before resetting it. Restore to a fresh volume and verify the API and example rows before switching over. Do not run `docker compose down -v` as a recovery step: it deletes the persisted catalog. The host Python backup script requires access to the volume's catalog directory; it is not included as a container maintenance interface.

## Diagnose interruption and corruption

Quiesce registration for a stable diagnostic report:

```python
from pathlib import Path
from llm_evaluation_hub.core.datasets import DatasetRepository

repo = DatasetRepository(Path("data/catalog"))
print(repo.inspect_storage())
```

| Symptom | Meaning and action |
| --- | --- |
| `missing` snapshot | Metadata references an absent file. Restore that file from a matching backup; do not silently return an empty example page. |
| `unreferenced` snapshot | It may be a registration killed after file publication but before metadata commit, or an abandoned seed stage. Confirm no writer is active and retain a backup before manual removal. No automatic garbage collection runs. |
| `.seed-stage-*` without database | Private incomplete copy. Startup leaves it untouched and can create another stage. Inspect before removing it manually. |
| `.starter` with publication marker and staged database | Seeding can validate and finish the pending publication under `.catalog.lock`. An ordinary repository initializer refuses to create an empty database over pending seed artifacts; resume with the seed configured first. Keep the same target path when resuming because the marker binds ownership to that path. |
| Unknown content with no database | Seeding rejects the target. Move your files deliberately or choose a fresh catalog root; startup never clears the directory. |
| SQLite lock timeout | The default busy timeout is 5 seconds. Identify the writer and retry after it finishes; never unlink `.catalog.lock` while processes exist. |
| Unsupported schema version | Startup refuses the catalog before running schema DDL. Use a compatible application or restore a compatible backup. No downgrade migration is provided. |
| Corrupt stored JSON or Parquet | API returns a generic server error. Check server diagnostics and restore a matching snapshot/index pair. Do not classify corruption as a client validation error. |

## Concurrency and durability

Startup and starter publication share a kernel file lock on Linux local filesystems. Process exit releases the lock. Ordinary reads and writes use separate SQLite connections, foreign keys and a 5 second timeout. WAL is configured during initialization. Registration processes source data before a short `BEGIN IMMEDIATE` metadata insert, so duplicate-name publication is serialized without holding a database write lock during processing.

Parquet is published before metadata. Ordinary insert failure removes its snapshot, but killing a process can leave an unreferenced file. There is no atomic transaction spanning SQLite and Parquet and no automatic deletion of unknown files. Do not edit snapshots in place. Network filesystems, native Windows, multi-user remote deployment and guaranteed recovery after host power loss require separate design and verification.
