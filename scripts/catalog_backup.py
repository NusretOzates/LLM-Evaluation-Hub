"""Create a consistent catalog backup without copying SQLite WAL files."""

import argparse
import shutil
import sqlite3
import tempfile
from pathlib import Path


def backup_catalog(source: Path, destination: Path) -> None:
    """Back up SQLite and its immutable referenced snapshots to a new directory.

    Snapshot files must not be modified/deleted by another process during the
    copy. Registration only adds immutable snapshots, so normal API tag edits
    and registrations can continue. Stop external file maintenance first.
    """
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("backup source and destination must not overlap")
    if destination.exists():
        raise FileExistsError("backup destination must not exist")
    database = source / "catalog.sqlite"
    if not database.is_file():
        raise FileNotFoundError("source catalog.sqlite does not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".catalog-backup-", dir=destination.parent
    ) as temporary:
        stage = Path(temporary)
        src = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
        dest = sqlite3.connect(stage / "catalog.sqlite")
        try:
            src.backup(dest)
            dest.execute("PRAGMA journal_mode = DELETE").fetchone()
            if dest.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("backup SQLite integrity check failed")
            for (relative,) in dest.execute("SELECT parquet_path FROM datasets"):
                relative_path = Path(relative)
                if relative_path.is_absolute() or ".." in relative_path.parts:
                    raise ValueError("catalog contains an unsafe snapshot path")
                snapshot = (source / relative_path).resolve()
                if not snapshot.is_relative_to(source):
                    raise ValueError("catalog contains an unsafe snapshot path")
                target = stage / relative_path
                if not target.resolve().is_relative_to(stage):
                    raise ValueError("backup snapshot target escapes staging")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snapshot, target)
        finally:
            dest.close()
            src.close()
        stage.rename(destination)


def main() -> None:
    """Parse source and new destination paths and create a complete backup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    backup_catalog(args.source, args.destination)


if __name__ == "__main__":
    main()
