"""Create the current catalog schema without upgrading older formats."""

import sqlite3
from pathlib import Path

from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection, catalog_lock

CATALOG_SCHEMA_VERSION = 6

_SCHEMA = """
CREATE TABLE tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES tags(id),
    path TEXT NOT NULL UNIQUE
);
CREATE TABLE datasets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    processor_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    repo_id TEXT,
    config TEXT,
    split TEXT,
    revision TEXT,
    resolved_sha TEXT,
    row_limit INTEGER,
    rows_loaded INTEGER NOT NULL,
    rows_kept INTEGER NOT NULL,
    rows_dropped INTEGER NOT NULL,
    segment_keys TEXT NOT NULL,
    parquet_path TEXT NOT NULL,
    snapshot_format_version INTEGER NOT NULL,
    trashed_at TEXT,
    purge_pending INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE dataset_tags (
    dataset_id TEXT NOT NULL REFERENCES datasets(id),
    tag_id TEXT NOT NULL REFERENCES tags(id),
    PRIMARY KEY (dataset_id, tag_id)
);
"""


_IMPORT_SCHEMA = """
CREATE TABLE processor_provenance (
    dataset_id TEXT PRIMARY KEY REFERENCES datasets(id),
    payload TEXT NOT NULL
);
CREATE TABLE import_previews (
    id TEXT PRIMARY KEY,
    spec TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE import_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    phase TEXT NOT NULL,
    rows_loaded INTEGER NOT NULL DEFAULT 0,
    rows_kept INTEGER NOT NULL DEFAULT 0,
    rows_dropped INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dataset_id TEXT REFERENCES datasets(id),
    error TEXT,
    spec TEXT NOT NULL,
    candidate_dataset_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE
);
"""


_INFERENCE_SCHEMA = """
CREATE TABLE inference_profiles (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE dataset_output_formats (
    dataset_id TEXT PRIMARY KEY REFERENCES datasets(id), payload TEXT NOT NULL
);
CREATE TABLE inference_runs (
    id TEXT PRIMARY KEY, state TEXT NOT NULL, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, spec TEXT NOT NULL, total INTEGER NOT NULL, error TEXT
);
CREATE TABLE inference_run_datasets (
    run_id TEXT NOT NULL REFERENCES inference_runs(id), dataset_id TEXT NOT NULL,
    name TEXT NOT NULL, snapshot_path TEXT NOT NULL, rows_kept INTEGER NOT NULL,
    output_format TEXT NOT NULL, snapshot_format_version INTEGER NOT NULL,
    PRIMARY KEY(run_id, dataset_id)
);
CREATE TABLE inference_results (
    run_id TEXT NOT NULL REFERENCES inference_runs(id), dataset_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY(run_id, dataset_id, ordinal)
);
"""


_EVALUATION_SCHEMA = """
CREATE TABLE evaluation_definitions (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, settings TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE evaluation_runs (
    id TEXT PRIMARY KEY, source_inference_run_id TEXT NOT NULL,
    state TEXT NOT NULL, settings TEXT NOT NULL, total INTEGER NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT
);
CREATE INDEX evaluation_source_dependency ON evaluation_runs(source_inference_run_id, state);
CREATE TABLE evaluation_run_datasets (
    run_id TEXT NOT NULL REFERENCES evaluation_runs(id), dataset_id TEXT NOT NULL,
    name TEXT NOT NULL, snapshot_path TEXT NOT NULL, snapshot_format_version INTEGER NOT NULL,
    rows_kept INTEGER NOT NULL, tags TEXT NOT NULL, PRIMARY KEY(run_id, dataset_id)
);
CREATE INDEX evaluation_dataset_dependency ON evaluation_run_datasets(dataset_id, run_id);
CREATE TABLE evaluation_inputs (
    run_id TEXT NOT NULL, dataset_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    source_index INTEGER NOT NULL, source_result_present INTEGER NOT NULL,
    source_status TEXT, segments TEXT NOT NULL,
    PRIMARY KEY(run_id, dataset_id, ordinal),
    FOREIGN KEY(run_id, dataset_id) REFERENCES evaluation_run_datasets(run_id, dataset_id)
);
CREATE TABLE evaluation_results (
    run_id TEXT NOT NULL, dataset_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    status TEXT NOT NULL, stage TEXT NOT NULL, result TEXT, scores TEXT, evidence TEXT,
    error TEXT, elapsed_ms REAL, attempts INTEGER NOT NULL DEFAULT 0, usage TEXT,
    PRIMARY KEY(run_id, dataset_id, ordinal),
    FOREIGN KEY(run_id, dataset_id, ordinal)
        REFERENCES evaluation_inputs(run_id, dataset_id, ordinal)
);
"""


def _create_schema(connection: sqlite3.Connection) -> None:
    """Initialize an empty database or accept the current format unchanged."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version == CATALOG_SCHEMA_VERSION:
        connection.execute("PRAGMA journal_mode = WAL").fetchone()
        return
    if (
        version != 0
        or connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
    ):
        raise RuntimeError(f"unsupported catalog schema version: {version}")
    connection.execute("PRAGMA journal_mode = WAL").fetchone()
    connection.executescript(_SCHEMA)
    connection.executescript(_IMPORT_SCHEMA)
    connection.executescript(_INFERENCE_SCHEMA)
    connection.executescript(_EVALUATION_SCHEMA)
    connection.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")


def initialize_catalog(root: Path) -> None:
    """Serialize initialization and refuse to bypass an unfinished seed publication."""
    with catalog_lock(root):
        if not (root / "catalog.sqlite").exists() and any(
            path.name == ".starter" or path.name.startswith(".seed-stage-")
            for path in root.iterdir()
        ):
            raise RuntimeError("pending starter publication: resume seeding before opening catalog")
        with catalog_connection(root) as connection:
            _create_schema(connection)
