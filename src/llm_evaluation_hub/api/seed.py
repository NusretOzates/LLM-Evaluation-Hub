"""Publish a complete starter catalog without clearing user-owned files."""

import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from llm_evaluation_hub.core.datasets.catalog.storage import catalog_lock

_STARTER = ".starter"
_MARKER = ".publication.json"
_SIDECARS = {"catalog.sqlite", "catalog.sqlite-wal", "catalog.sqlite-shm"}


def ensure_starter_catalog(catalog: Path, seed: Path) -> bool:
    """Stage a starter and publish its database last under the startup lock.

    Only Linux local filesystems are supported. An existing database wins.
    Unknown target content is never removed. A completed .starter publication
    can resume after process death. Incomplete .seed-stage-* directories remain
    unreferenced for operator inspection; they are never automatically deleted.
    This provides process-restart recovery, not power-loss durability.
    """
    catalog, seed = catalog.resolve(), seed.resolve()
    if catalog == seed or catalog in seed.parents or seed in catalog.parents:
        raise ValueError("starter and target directories must not overlap")
    database = catalog / "catalog.sqlite"
    with catalog_lock(catalog):
        if database.is_file():
            return False
        source = seed / "catalog.sqlite"
        if not source.is_file():
            raise FileNotFoundError(f"starter catalog is missing catalog.sqlite: {seed}")
        _require_integrity(source)
        _require_owned_target(catalog)
        starter = catalog / _STARTER
        if not starter.exists():
            _stage_catalog(seed, catalog)
        marker = json.loads((starter / _MARKER).read_text())
        if marker != {"format": 1, "target": str(catalog)}:
            raise RuntimeError("unrecognized starter publication marker")
        staged_database = starter / "catalog.sqlite"
        _require_integrity(staged_database)
        _require_snapshots(staged_database, catalog)
        staged_database.replace(database)
        return True


def _require_owned_target(catalog: Path) -> None:
    """Reject unrelated content before any publication mutation."""
    for child in catalog.iterdir():
        if child.name == ".catalog.lock":
            continue
        if (
            child.name == _STARTER
            and child.is_dir()
            and not child.is_symlink()
            and (child / _MARKER).is_file()
        ):
            continue
        if child.name.startswith(".seed-stage-") and child.is_dir() and not child.is_symlink():
            # Never remove these. They are not made visible by the database.
            continue
        raise RuntimeError(f"refusing to seed nonempty catalog: {child.name}")


def _stage_catalog(seed: Path, catalog: Path) -> None:
    """Copy into a private directory, then atomically publish the payload tree."""
    with tempfile.TemporaryDirectory(prefix=".seed-stage-", dir=catalog) as temporary:
        stage = Path(temporary)
        for path in sorted(seed.rglob("*")):
            if path.is_symlink():
                raise ValueError("starter catalogs must not contain symlinks")
            if not path.is_file() or path.name in _SIDECARS:
                continue
            target = stage / path.relative_to(seed)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        staged_database = stage / "catalog.sqlite"
        _backup_sqlite(seed / "catalog.sqlite", staged_database)
        with closing(sqlite3.connect(staged_database)) as connection, connection:
            has_datasets = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='datasets'"
            ).fetchone()
            if has_datasets:
                for dataset_id, relative in connection.execute(
                    "SELECT id, parquet_path FROM datasets"
                ):
                    source_path = (seed / relative).resolve()
                    if not source_path.is_relative_to(seed) or not source_path.is_file():
                        raise RuntimeError("starter references a missing or unsafe snapshot")
                    connection.execute(
                        "UPDATE datasets SET parquet_path = ? WHERE id = ?",
                        (f"{_STARTER}/{relative}", dataset_id),
                    )
        _require_integrity(staged_database)
        (stage / _MARKER).write_text(json.dumps({"format": 1, "target": str(catalog)}))
        stage.rename(catalog / _STARTER)


def _require_snapshots(database: Path, catalog: Path) -> None:
    """Check published paths before making metadata visible."""
    with closing(sqlite3.connect(database)) as connection:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='datasets'"
        ).fetchone():
            return
        for (relative,) in connection.execute("SELECT parquet_path FROM datasets"):
            path = (catalog / relative).resolve()
            if not path.is_relative_to(catalog / _STARTER) or not path.is_file():
                raise RuntimeError("starter references a missing or unsafe snapshot")


def _require_integrity(database: Path) -> None:
    """Reject a SQLite database whose integrity check is not ok."""
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    if row is None or row[0] != "ok":
        raise RuntimeError("starter database failed integrity check")


def _backup_sqlite(source: Path, dest: Path) -> None:
    """Write a consistent SQLite snapshot, including committed WAL frames."""
    source_connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    dest_connection = sqlite3.connect(dest)
    try:
        source_connection.backup(dest_connection)
        dest_connection.execute("PRAGMA journal_mode = DELETE").fetchone()
    finally:
        dest_connection.close()
        source_connection.close()
