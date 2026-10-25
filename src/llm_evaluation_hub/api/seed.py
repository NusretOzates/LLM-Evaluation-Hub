"""Publish a starter catalog when the target has no SQLite file."""

import shutil
import sqlite3
from pathlib import Path

_SQLITE_SIDECARS = {
    "catalog.sqlite",
    "catalog.sqlite-wal",
    "catalog.sqlite-shm",
    ".catalog.sqlite.partial",
}


def ensure_starter_catalog(catalog: Path, seed: Path) -> bool:
    """Copy `seed` into `catalog` when `catalog` has no SQLite database.

    An existing `catalog.sqlite` is left in place, including after a process
    restart. A copy that stopped before that file was published is removed and
    copied again. The database file is published last, by rename.

    Args:
        catalog: Directory that should contain `catalog.sqlite`.
        seed: Directory that already contains a starter `catalog.sqlite`.

    Returns:
        True when the starter catalog was published. False when `catalog`
        already had a database file.

    Raises:
        FileNotFoundError: `seed` has no `catalog.sqlite`.
        RuntimeError: The starter database fails `PRAGMA integrity_check`.
        sqlite3.DatabaseError: `seed` is not a SQLite database.
    """
    database = catalog / "catalog.sqlite"
    if database.is_file():
        return False
    seed_database = seed / "catalog.sqlite"
    if not seed_database.is_file():
        raise FileNotFoundError(f"starter catalog is missing catalog.sqlite: {seed}")
    _require_integrity(seed_database)
    catalog.mkdir(parents=True, exist_ok=True)
    _clear_directory(catalog)
    _copy_payload(seed, catalog)
    partial = catalog / ".catalog.sqlite.partial"
    _backup_sqlite(seed_database, partial)
    _require_integrity(partial)
    partial.replace(database)
    return True


def _require_integrity(database: Path) -> None:
    """Raise when `database` is missing pages or is not SQLite."""
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    if row is None or row[0] != "ok":
        detail = "no result" if row is None else row[0]
        raise RuntimeError(f"catalog failed integrity check at {database}: {detail}")


def _clear_directory(directory: Path) -> None:
    """Remove every child of `directory` and leave the directory itself."""
    for child in directory.iterdir():
        if child.is_symlink() or not child.is_dir():
            child.unlink()
        else:
            shutil.rmtree(child)


def _copy_payload(seed: Path, catalog: Path) -> None:
    """Copy snapshot files, leaving the SQLite database for a later rename."""
    for path in sorted(seed.rglob("*")):
        if not path.is_file() or path.name in _SQLITE_SIDECARS:
            continue
        relative = path.relative_to(seed)
        target = catalog / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _backup_sqlite(source: Path, dest: Path) -> None:
    """Write a consistent SQLite snapshot, including any WAL frames."""
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dest_connection = sqlite3.connect(dest)
    try:
        source_connection.backup(dest_connection)
    finally:
        dest_connection.close()
        source_connection.close()
