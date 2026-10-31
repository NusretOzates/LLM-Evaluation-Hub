"""Versioned catalog migration, shared by datasets and import persistence."""

import sqlite3
from pathlib import Path

from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection, catalog_lock

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES tags(id),
    path TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS datasets (
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
    parquet_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset_tags (
    dataset_id TEXT NOT NULL REFERENCES datasets(id),
    tag_id TEXT NOT NULL REFERENCES tags(id),
    PRIMARY KEY (dataset_id, tag_id)
);
"""


_IMPORT_SCHEMA = """
CREATE TABLE IF NOT EXISTS processor_provenance (
    dataset_id TEXT PRIMARY KEY REFERENCES datasets(id),
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_previews (
    id TEXT PRIMARY KEY,
    spec TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_jobs (
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


def migrate(connection: sqlite3.Connection) -> None:
    """Upgrade metadata without rewriting existing immutable snapshots."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1, 2, 3):
        raise RuntimeError(f"unsupported catalog schema version: {version}")
    connection.execute("PRAGMA journal_mode = WAL").fetchone()
    connection.executescript(_SCHEMA)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(datasets)")}
    if "snapshot_format_version" not in columns:
        connection.execute(
            "ALTER TABLE datasets ADD COLUMN snapshot_format_version INTEGER NOT NULL DEFAULT 1"
        )
    if "trashed_at" not in columns:
        connection.execute("ALTER TABLE datasets ADD COLUMN trashed_at TEXT")
    if "purge_pending" not in columns:
        connection.execute(
            "ALTER TABLE datasets ADD COLUMN purge_pending INTEGER NOT NULL DEFAULT 0"
        )
    connection.executescript(_IMPORT_SCHEMA)
    connection.execute("PRAGMA user_version = 3")


def initialize_catalog(root: Path) -> None:
    """Serialize migration and refuse to bypass an unfinished seed publication."""
    with catalog_lock(root):
        if not (root / "catalog.sqlite").exists() and any(
            path.name == ".starter" or path.name.startswith(".seed-stage-")
            for path in root.iterdir()
        ):
            raise RuntimeError("pending starter publication: resume seeding before opening catalog")
        with catalog_connection(root) as connection:
            migrate(connection)
