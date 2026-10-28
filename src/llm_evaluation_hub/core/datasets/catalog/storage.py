"""Catalog initialization ownership and filesystem diagnostics for Linux local disks."""

import fcntl
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def catalog_lock(root: Path) -> Generator[None, None, None]:
    """Serialize startup across processes. The kernel releases the lock on exit.

    Keep the lock file in place: unlinking it could let new processes lock a
    different inode. All initializers, including seed publication, use this lock.
    """
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".catalog.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@contextmanager
def catalog_connection(root: Path) -> Generator[sqlite3.Connection, None, None]:
    """Commit shared catalog writes on success, rolling back failures."""
    connection = sqlite3.connect(root / "catalog.sqlite")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
