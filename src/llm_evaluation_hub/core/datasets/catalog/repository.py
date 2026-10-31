"""SQLite catalog and Parquet snapshots for processed datasets."""

import json
import os
import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict

from llm_evaluation_hub.core.datasets.catalog.errors import (
    DatasetInUseError,
    DuplicateDatasetError,
    UnknownDatasetError,
)
from llm_evaluation_hub.core.datasets.catalog.imports import complete_import
from llm_evaluation_hub.core.datasets.catalog.schema import initialize_catalog
from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection
from llm_evaluation_hub.core.datasets.catalog.tags import Tag, TagStore
from llm_evaluation_hub.core.datasets.processing import (
    EmptyDatasetError,
    ProcessResult,
    RowProcessor,
    process_rows,
    validate_segment_declaration,
)
from llm_evaluation_hub.core.datasets.records import (
    JsonValue,
    ProcessedExample,
    decode_message,
    dump_json,
    parse_json_value,
)
from llm_evaluation_hub.core.datasets.sources import DatasetSource, SourceDescriptor


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
    snapshot_format_version: int


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
    provenance: dict[str, object] | None
    output_format: dict[str, JsonValue] | None
    import_id: str | None


class DatasetRepository:
    """Local catalog of processed datasets, tag links, and Parquet snapshots."""

    def __init__(self, root: Path) -> None:
        """Create the catalog directory and SQLite schema when they are missing."""
        self._root = root
        initialize_catalog(root)

    def create_tag(self, name: str, parent: str | None = None) -> Tag:
        """Create a tag node. This does not attach the tag to a dataset."""
        with catalog_connection(self._root) as connection:
            return TagStore(connection).create(name, parent)

    def delete_tag(self, path: str, *, promote_children: bool = False) -> None:
        """Delete a subtree or delete its grouping and promote its children."""
        with catalog_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            TagStore(connection).delete(path, promote_children=promote_children)

    def tag_impact(self, path: str) -> tuple[list[str], int]:
        """Return the full affected subtree and distinct linked dataset count."""
        with catalog_connection(self._root) as connection:
            return TagStore(connection).impact(path)

    def trash(self, dataset_id: str) -> None:
        """Move a dataset to trash, leaving its snapshot and shared tags intact."""
        with catalog_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM datasets WHERE id = ?", (dataset_id,)
            ).fetchone()
            if row is None:
                raise UnknownDatasetError(dataset_id)
            connection.execute(
                "UPDATE datasets SET trashed_at = COALESCE(trashed_at, ?) WHERE id = ?",
                (datetime.now(UTC).isoformat(), dataset_id),
            )

    def restore(self, dataset_id: str) -> None:
        """Restore a trashed dataset; names remain reserved while in trash."""
        with catalog_connection(self._root) as connection:
            cursor = connection.execute(
                "UPDATE datasets SET trashed_at = NULL WHERE id = ? AND purge_pending = 0",
                (dataset_id,),
            )
            if cursor.rowcount == 0:
                raise UnknownDatasetError(dataset_id)

    def list_trash(self) -> list[DatasetRecord]:
        """List datasets retained in trash."""
        with catalog_connection(self._root) as connection:
            rows = connection.execute(
                "SELECT * FROM datasets WHERE trashed_at IS NOT NULL ORDER BY name"
            ).fetchall()
            return [self._record(connection, row) for row in rows]

    def purge(self, dataset_id: str) -> None:
        """Permanently remove a trashed snapshot, with a retryable cleanup marker."""
        with catalog_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM datasets WHERE id = ?", (dataset_id,)
            ).fetchone()
            if row is None:
                return
            if row["trashed_at"] is None:
                raise ValueError("dataset must be in trash before permanent deletion")
            dependency = connection.execute(
                "SELECT 1 FROM inference_run_datasets d JOIN inference_runs r ON r.id = d.run_id "
                "WHERE d.dataset_id = ? AND r.state IN ('queued', "
                "'running', 'interrupted', 'canceling') LIMIT 1",
                (dataset_id,),
            ).fetchone()
            if dependency is not None:
                raise DatasetInUseError("dataset is required by an unfinished inference run")
            canonical = f"datasets/{dataset_id}/rows.parquet"
            if row["parquet_path"] != canonical or str(uuid.UUID(dataset_id)) != dataset_id:
                raise ValueError("snapshot is not at its owned path")
            root = self._root.resolve()
            snapshot = self._root / canonical
            if snapshot.resolve().parent != root / "datasets" / dataset_id:
                raise ValueError("snapshot path escapes its owned directory")
            connection.execute("UPDATE datasets SET purge_pending = 1 WHERE id = ?", (dataset_id,))
        snapshot.unlink(missing_ok=True)
        with catalog_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE import_jobs SET dataset_id = NULL WHERE dataset_id = ?", (dataset_id,)
            )
            connection.execute(
                "DELETE FROM processor_provenance WHERE dataset_id = ?", (dataset_id,)
            )
            connection.execute(
                "DELETE FROM dataset_output_formats WHERE dataset_id = ?", (dataset_id,)
            )
            connection.execute("DELETE FROM dataset_tags WHERE dataset_id = ?", (dataset_id,))
            connection.execute(
                "DELETE FROM datasets WHERE id = ? AND purge_pending = 1", (dataset_id,)
            )

    def list_tags(self) -> list[Tag]:
        """Return every tag node, ordered by path."""
        with catalog_connection(self._root) as connection:
            return TagStore(connection).list_tags()

    def ensure_path(self, segments: Sequence[str]) -> tuple[Tag, bool]:
        """Create missing nodes on one path. Return the leaf and whether any node was new."""
        with catalog_connection(self._root) as connection:
            return _ensure_segments(TagStore(connection), segments)

    def ensure_paths(self, paths: Sequence[Sequence[str]]) -> bool:
        """Create every missing node on these paths in one transaction."""
        if len(paths) == 0:
            raise ValueError("tag path must not be empty")
        with catalog_connection(self._root) as connection:
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
        result = process_rows(frame.iter_rows(named=True), processor, segment_keys)
        descriptor = source.describe()
        return self.register_processed(
            name,
            result,
            descriptor,
            processor_id=processor_id,
            tags=tag_paths,
            segments=segment_keys,
            limit=limit,
        )

    def register_processed(  # noqa: PLR0913
        self,
        name: str,
        result: ProcessResult,
        descriptor: SourceDescriptor,
        *,
        processor_id: str,
        tags: Sequence[str] = (),
        segments: Sequence[str] = (),
        limit: int | None = None,
        provenance: dict[str, object] | None = None,
        output_format: dict[str, JsonValue] | None = None,
        dataset_id: str | None = None,
        import_id: str | None = None,
    ) -> DatasetRecord:
        """Publish a finished result, provenance and job success atomically.

        Import supervisors must finish their child and hold ImportStore.decision_lock
        before calling this method. No source or processor executes during publication.
        """
        self._validate_request(name, processor_id, limit)
        segment_keys = validate_segment_declaration(segments)
        tag_paths = tuple(tags)
        self._require_available(name, tag_paths)
        if result.rows_kept < 1 or result.frame.height < 1:
            raise EmptyDatasetError()
        if provenance is not None:
            parse_json_value(provenance)
        if output_format is not None:
            parse_json_value(output_format)
        dataset_id = str(uuid.uuid4()) if dataset_id is None else str(uuid.UUID(dataset_id))
        relative_path = f"datasets/{dataset_id}/rows.parquet"
        final_path = self._root / relative_path
        if final_path.exists():
            raise ValueError("candidate snapshot already exists")
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
            provenance=provenance,
            output_format=output_format,
            import_id=import_id,
        )
        try:
            self._insert(stored)
        except Exception:
            final_path.unlink(missing_ok=True)
            raise
        return self.get(name)

    def add_tags(self, name: str, tags: Sequence[str]) -> DatasetRecord:
        """Link existing tags to a dataset. Existing links stay in place."""
        with catalog_connection(self._root) as connection:
            dataset_id = self._dataset_id(connection, name)
            TagStore(connection).link(dataset_id, tags)
        return self.get(name)

    def remove_tags(self, name: str, tags: Sequence[str]) -> DatasetRecord:
        """Remove links to existing tags. The tag nodes stay in the tree."""
        with catalog_connection(self._root) as connection:
            dataset_id = self._dataset_id(connection, name)
            TagStore(connection).unlink(dataset_id, tags)
        return self.get(name)

    def get(self, name: str) -> DatasetRecord:
        """Return one dataset and the tag paths linked directly to it."""
        with catalog_connection(self._root) as connection:
            return self._record(connection, self._dataset_row(connection, name))

    def get_by_id(self, dataset_id: str) -> DatasetRecord:
        """Return a dataset by its immutable transport identity."""
        with catalog_connection(self._root) as connection:
            row = connection.execute(
                "SELECT * FROM datasets WHERE id = ?", (dataset_id,)
            ).fetchone()
            if row is None:
                raise UnknownDatasetError(dataset_id)
            return self._record(connection, row)

    def get_processor(self, dataset_id: str) -> dict[str, object] | None:
        """Return stored processor provenance, or explicit absence for Python datasets."""
        self.get_by_id(dataset_id)
        with catalog_connection(self._root) as connection:
            row = connection.execute(
                "SELECT payload FROM processor_provenance WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()
            return None if row is None else json.loads(row["payload"])

    def inspect_storage(self) -> dict[str, list[str]]:
        """Report missing and unreferenced snapshots without modifying files.

        Quiesce registration for a stable report: a file may be published just
        before its metadata transaction commits.
        """
        expected = {record.parquet_path for record in [*self.list_datasets(), *self.list_trash()]}
        actual = {str(path.relative_to(self._root)) for path in self._root.rglob("*.parquet")}
        return {"missing": sorted(expected - actual), "unreferenced": sorted(actual - expected)}

    def list_datasets(self, *, tag: str | None = None) -> list[DatasetRecord]:
        """List datasets. A tag path also matches datasets tagged below that node."""
        with catalog_connection(self._root) as connection:
            if tag is None:
                rows = connection.execute(
                    "SELECT * FROM datasets WHERE trashed_at IS NULL ORDER BY name"
                ).fetchall()
            else:
                tag_ids = TagStore(connection).descendant_ids(tag)
                placeholders = ", ".join("?" for _ in tag_ids)
                rows = connection.execute(
                    f"""
                    SELECT DISTINCT datasets.*
                    FROM datasets
                    JOIN dataset_tags ON dataset_tags.dataset_id = datasets.id
                    WHERE datasets.trashed_at IS NULL AND dataset_tags.tag_id IN ({placeholders})
                    ORDER BY datasets.name
                    """,
                    tag_ids,
                ).fetchall()
            tags_by_id: dict[str, list[str]] = {}
            for link in connection.execute(
                "SELECT dataset_id, tags.path FROM dataset_tags "
                "JOIN tags ON tags.id = dataset_tags.tag_id ORDER BY tags.path"
            ):
                tags_by_id.setdefault(link["dataset_id"], []).append(link["path"])
            return [self._record(connection, row, tags_by_id.get(row["id"], [])) for row in rows]

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
        if record.snapshot_format_version != 2:
            raise ValueError(f"unsupported snapshot format: {record.snapshot_format_version}")
        examples: list[ProcessedExample] = []
        for row in frame.iter_rows(named=True):
            conversation = [decode_message(item) for item in json.loads(row["conversation"])]
            expected = row["expected_output"]
            examples.append(
                ProcessedExample(
                    conversation=conversation,
                    expected_output=None if expected is None else json.loads(expected),
                    extras=json.loads(row["extras"]),
                    tools=json.loads(row["tools"]),
                    segments={key: row[key] for key in record.segment_keys},
                )
            )
        return examples

    def inference_rows(
        self, dataset_id: str, *, offset: int = 0, limit: int = 100
    ) -> list[tuple[int, int, ProcessedExample]]:
        """Read a bounded retained-row page by ID, including trashed snapshots."""
        if offset < 0 or limit < 1:
            raise ValueError("invalid row page")
        record = self.get_by_id(dataset_id)
        if record.snapshot_format_version != 2:
            raise ValueError(f"unsupported snapshot format: {record.snapshot_format_version}")
        frame = pl.scan_parquet(self._root / record.parquet_path).slice(offset, limit).collect()
        result = []
        for ordinal, row in enumerate(frame.iter_rows(named=True), start=offset):
            example = ProcessedExample(
                conversation=[decode_message(item) for item in json.loads(row["conversation"])],
                tools=json.loads(row["tools"]),
            )
            result.append((ordinal, row["source_index"], example))
        return result

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
        with catalog_connection(self._root) as connection:
            if self._name_exists(connection, name):
                raise DuplicateDatasetError(name)
            store = TagStore(connection)
            for path in tags:
                store.require(path)

    def _write_parquet(self, frame: pl.DataFrame, final_path: Path) -> None:
        """Atomically link a staged snapshot without replacing existing candidates."""
        temp_path = self._root / "tmp" / f"{final_path.parent.name}-{uuid.uuid4()}.parquet"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            frame.write_parquet(temp_path)
            os.link(temp_path, final_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _insert(self, stored: _NewDataset) -> None:
        """Insert the dataset row and tag links after the Parquet file exists."""
        with catalog_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
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
                    rows_dropped, segment_keys, parquet_path, snapshot_format_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    2,
                ),
            )
            store.link(stored.dataset_id, stored.tags)
            if stored.output_format is not None:
                connection.execute(
                    "INSERT INTO dataset_output_formats(dataset_id, payload) VALUES (?, ?)",
                    (stored.dataset_id, dump_json(stored.output_format)),
                )
            if stored.provenance is not None:
                connection.execute(
                    "INSERT INTO processor_provenance(dataset_id, payload) VALUES (?, ?)",
                    (stored.dataset_id, dump_json(stored.provenance)),
                )
            if stored.import_id is not None:
                complete_import(
                    connection,
                    stored.import_id,
                    stored.dataset_id,
                    (stored.rows_loaded, stored.rows_kept, stored.rows_dropped),
                )

    def _record(
        self, connection: sqlite3.Connection, row: sqlite3.Row, tags: list[str] | None = None
    ) -> DatasetRecord:
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
            tags=TagStore(connection).paths_for(row["id"]) if tags is None else tags,
            parquet_path=row["parquet_path"],
            snapshot_format_version=row["snapshot_format_version"],
        )

    def _dataset_row(self, connection: sqlite3.Connection, name: str) -> sqlite3.Row:
        """Return the dataset row or raise when the name is missing."""
        row = connection.execute(
            "SELECT * FROM datasets WHERE name = ? AND trashed_at IS NULL", (name,)
        ).fetchone()
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
