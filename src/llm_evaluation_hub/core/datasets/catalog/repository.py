"""SQLite catalog and Parquet snapshots for processed datasets."""

import json
import os
import sqlite3
import uuid
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict

from llm_evaluation_hub.core.datasets.catalog.errors import (
    DuplicateDatasetError,
    UnknownDatasetError,
)
from llm_evaluation_hub.core.datasets.catalog.tags import Tag, TagStore
from llm_evaluation_hub.core.datasets.processing import (
    RowProcessor,
    process_rows,
    validate_segment_declaration,
)
from llm_evaluation_hub.core.datasets.records import ProcessedExample, decode_message
from llm_evaluation_hub.core.datasets.sources import DatasetSource, SourceDescriptor

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


class DatasetRecord(BaseModel):
    """Metadata for one registered snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    created_at: datetime
    processor_id: str
    source_type: str
    repo_id: str | None
    config: str | None
    split: str | None
    revision: str | None
    resolved_sha: str | None
    row_limit: int | None
    rows_loaded: int
    rows_kept: int
    rows_dropped: int
    segment_keys: list[str]
    tags: list[str]
    parquet_path: str


@dataclass(frozen=True)
class _NewDataset:
    """Values inserted after a snapshot file is in place."""

    dataset_id: str
    name: str
    processor_id: str
    descriptor: SourceDescriptor
    row_limit: int | None
    rows_loaded: int
    rows_kept: int
    rows_dropped: int
    segment_keys: list[str]
    parquet_path: str
    tags: tuple[str, ...]


class DatasetRepository:
    """Local catalog of processed datasets, tag links, and Parquet snapshots."""

    def __init__(self, root: Path) -> None:
        """Create the catalog directory and SQLite schema when they are missing."""
        self._root = root
        with self._connection():
            pass

    def create_tag(self, name: str, parent: str | None = None) -> Tag:
        """Create a tag node. This does not attach the tag to a dataset."""
        with self._connection() as connection:
            return TagStore(connection).create(name, parent)

    def delete_tag(self, path: str) -> None:
        """Delete a tag that has no children and no dataset links."""
        with self._connection() as connection:
            TagStore(connection).delete(path)

    def list_tags(self) -> list[Tag]:
        """Return every tag node, ordered by path."""
        with self._connection() as connection:
            return TagStore(connection).list_tags()

    def ensure_path(self, segments: Sequence[str]) -> tuple[Tag, bool]:
        """Create missing nodes on one path. Return the leaf and whether any node was new."""
        with self._connection() as connection:
            return _ensure_segments(TagStore(connection), segments)

    def ensure_paths(self, paths: Sequence[Sequence[str]]) -> bool:
        """Create every missing node on these paths in one transaction."""
        if len(paths) == 0:
            raise ValueError("tag path must not be empty")
        with self._connection() as connection:
            store = TagStore(connection)
            created_any = False
            for segments in paths:
                _, created = _ensure_segments(store, segments)
                created_any = created_any or created
            return created_any

    def register(  # noqa: PLR0913
        self,
        name: str,
        source: DatasetSource,
        processor: RowProcessor,
        *,
        processor_id: str,
        tags: Sequence[str] = (),
        segments: Sequence[str] = (),
        limit: int | None = None,
    ) -> DatasetRecord:
        """Process a source and store a new snapshot under `name`."""
        self._validate_request(name, processor_id, limit)
        segment_keys = validate_segment_declaration(segments)
        tag_paths = tuple(tags)
        self._require_available(name, tag_paths)
        frame = source.read(limit=limit)
        result = process_rows(frame, processor, segment_keys)
        descriptor = source.describe()
        dataset_id = str(uuid.uuid4())
        relative_path = f"datasets/{dataset_id}/rows.parquet"
        final_path = self._root / relative_path
        self._write_parquet(result.frame, final_path)
        stored = _NewDataset(
            dataset_id=dataset_id,
            name=name,
            processor_id=processor_id,
            descriptor=descriptor,
            row_limit=limit,
            rows_loaded=result.rows_loaded,
            rows_kept=result.rows_kept,
            rows_dropped=result.rows_dropped,
            segment_keys=segment_keys,
            parquet_path=relative_path,
            tags=tag_paths,
        )
        try:
            self._insert(stored)
        except Exception:
            final_path.unlink(missing_ok=True)
            raise
        return self.get(name)

    def add_tags(self, name: str, tags: Sequence[str]) -> DatasetRecord:
        """Link existing tags to a dataset. Existing links stay in place."""
        with self._connection() as connection:
            dataset_id = self._dataset_id(connection, name)
            TagStore(connection).link(dataset_id, tags)
        return self.get(name)

    def remove_tags(self, name: str, tags: Sequence[str]) -> DatasetRecord:
        """Remove links to existing tags. The tag nodes stay in the tree."""
        with self._connection() as connection:
            dataset_id = self._dataset_id(connection, name)
            TagStore(connection).unlink(dataset_id, tags)
        return self.get(name)

    def get(self, name: str) -> DatasetRecord:
        """Return one dataset and the tag paths linked directly to it."""
        with self._connection() as connection:
            return self._record(connection, self._dataset_row(connection, name))

    def list_datasets(self, *, tag: str | None = None) -> list[DatasetRecord]:
        """List datasets. A tag path also matches datasets tagged below that node."""
        with self._connection() as connection:
            if tag is None:
                rows = connection.execute("SELECT * FROM datasets ORDER BY name").fetchall()
            else:
                tag_ids = TagStore(connection).descendant_ids(tag)
                placeholders = ", ".join("?" for _ in tag_ids)
                rows = connection.execute(
                    f"""
                    SELECT DISTINCT datasets.*
                    FROM datasets
                    JOIN dataset_tags ON dataset_tags.dataset_id = datasets.id
                    WHERE dataset_tags.tag_id IN ({placeholders})
                    ORDER BY datasets.name
                    """,
                    tag_ids,
                ).fetchall()
            return [self._record(connection, row) for row in rows]

    def rows(self, name: str) -> pl.DataFrame:
        """Read the stored Parquet snapshot."""
        record = self.get(name)
        return pl.scan_parquet(self._root / record.parquet_path).collect()

    def examples(
        self,
        name: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ProcessedExample]:
        """Parse a page of the snapshot back into conversation records."""
        if offset < 0:
            raise ValueError("offset must be at least 0")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        record = self.get(name)
        scan = pl.scan_parquet(self._root / record.parquet_path)
        if limit is None and offset == 0:
            frame = scan.collect()
        else:
            frame = scan.slice(offset, limit).collect()
        examples: list[ProcessedExample] = []
        for row in frame.iter_rows(named=True):
            conversation = [decode_message(item) for item in json.loads(row["conversation"])]
            expected = row["expected_output"]
            examples.append(
                ProcessedExample(
                    conversation=conversation,
                    expected_output=None if expected is None else json.loads(expected),
                    extras=json.loads(row["extras"]),
                    segments={key: row[key] for key in record.segment_keys},
                )
            )
        return examples

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a connection and commit when the body returns."""
        self._root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._root / "catalog.sqlite")
        connection.row_factory = sqlite3.Row
        # WAL plus a busy timeout lets the next process reopen after a kill.
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL").fetchone()
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            connection.executescript(_SCHEMA)
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _validate_request(self, name: str, processor_id: str, limit: int | None) -> None:
        """Reject an empty identity or a non-positive limit."""
        if name == "":
            raise ValueError("dataset name must not be empty")
        if processor_id == "":
            raise ValueError("processor_id must not be empty")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")

    def _require_available(self, name: str, tags: Sequence[str]) -> None:
        """Fail before reading the source when the name or a tag path is unusable."""
        with self._connection() as connection:
            if self._name_exists(connection, name):
                raise DuplicateDatasetError(name)
            store = TagStore(connection)
            for path in tags:
                store.require(path)

    def _write_parquet(self, frame: pl.DataFrame, final_path: Path) -> None:
        """Write a temp Parquet file and move it into the snapshot path."""
        temp_path = self._root / "tmp" / f"{final_path.parent.name}.parquet"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            frame.write_parquet(temp_path)
            os.replace(temp_path, final_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _insert(self, stored: _NewDataset) -> None:
        """Insert the dataset row and tag links after the Parquet file exists."""
        with self._connection() as connection:
            if self._name_exists(connection, stored.name):
                raise DuplicateDatasetError(stored.name)
            store = TagStore(connection)
            for path in stored.tags:
                store.require(path)
            descriptor = stored.descriptor
            connection.execute(
                """
                INSERT INTO datasets (
                    id, name, created_at, processor_id, source_type, repo_id, config,
                    split, revision, resolved_sha, row_limit, rows_loaded, rows_kept,
                    rows_dropped, segment_keys, parquet_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.dataset_id,
                    stored.name,
                    datetime.now(UTC).isoformat(),
                    stored.processor_id,
                    descriptor.source_type,
                    descriptor.repo_id,
                    descriptor.config,
                    descriptor.split,
                    descriptor.revision,
                    descriptor.resolved_sha,
                    stored.row_limit,
                    stored.rows_loaded,
                    stored.rows_kept,
                    stored.rows_dropped,
                    json.dumps(stored.segment_keys),
                    stored.parquet_path,
                ),
            )
            store.link(stored.dataset_id, stored.tags)

    def _record(self, connection: sqlite3.Connection, row: sqlite3.Row) -> DatasetRecord:
        """Map a dataset row and its direct tag links to the public record."""
        return DatasetRecord(
            id=row["id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            processor_id=row["processor_id"],
            source_type=row["source_type"],
            repo_id=row["repo_id"],
            config=row["config"],
            split=row["split"],
            revision=row["revision"],
            resolved_sha=row["resolved_sha"],
            row_limit=row["row_limit"],
            rows_loaded=row["rows_loaded"],
            rows_kept=row["rows_kept"],
            rows_dropped=row["rows_dropped"],
            segment_keys=json.loads(row["segment_keys"]),
            tags=TagStore(connection).paths_for(row["id"]),
            parquet_path=row["parquet_path"],
        )

    def _dataset_row(self, connection: sqlite3.Connection, name: str) -> sqlite3.Row:
        """Return the dataset row or raise when the name is missing."""
        row = connection.execute("SELECT * FROM datasets WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise UnknownDatasetError(name)
        return row

    def _dataset_id(self, connection: sqlite3.Connection, name: str) -> str:
        """Return the dataset id for a name."""
        return self._dataset_row(connection, name)["id"]

    def _name_exists(self, connection: sqlite3.Connection, name: str) -> bool:
        """Report whether a dataset name is already stored."""
        row = connection.execute("SELECT 1 FROM datasets WHERE name = ?", (name,)).fetchone()
        return row is not None


def _ensure_segments(store: TagStore, segments: Sequence[str]) -> tuple[Tag, bool]:
    """Insert any missing segment and return the leaf plus whether a node was new."""
    if len(segments) == 0:
        raise ValueError("tag path must not be empty")
    leaf, created_any = store.ensure(segments[0], None)
    parent = leaf.path
    for name in segments[1:]:
        leaf, created = store.ensure(name, parent)
        parent = leaf.path
        created_any = created_any or created
    return leaf, created_any


__all__ = ["DatasetRecord", "DatasetRepository"]
