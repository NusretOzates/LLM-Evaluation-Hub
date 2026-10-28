"""Import publication, legacy snapshots, and shared backup/seed persistence."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from scripts.catalog_backup import backup_catalog

from llm_evaluation_hub.api.seed import ensure_starter_catalog
from llm_evaluation_hub.core.datasets.catalog import (
    DatasetRecord,
    DatasetRepository,
    IdempotencyConflictError,
    ImportStateError,
    ImportStore,
)
from llm_evaluation_hub.core.datasets.processing import (
    EmptyDatasetError,
    ProcessResult,
    process_rows,
)
from llm_evaluation_hub.core.datasets.records import ProcessedExample
from llm_evaluation_hub.core.datasets.sources import SourceDescriptor


def _processor(row: dict[str, object]) -> ProcessedExample:
    name = str(row["name"])
    return ProcessedExample.model_validate(
        {
            "conversation": [{"role": "user", "content": name}],
            "tools": []
            if name == "none"
            else [
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "parameters": {
                            "$defs": {"key": {"type": "string"}},
                            "properties": {"id": {"$ref": "#/$defs/key"}},
                        },
                    },
                }
            ],
        }
    )


def _result() -> ProcessResult:
    return process_rows(({"name": name} for name in ("lookup", "search", "none")), _processor, [])


def _publish(
    repository: DatasetRepository,
    *,
    dataset_id: str | None = None,
    import_id: str | None = None,
    provenance: dict[str, object] | None = None,
) -> DatasetRecord:
    return repository.register_processed(
        "imported",
        _result(),
        SourceDescriptor(source_type="memory"),
        processor_id="tests.import",
        dataset_id=dataset_id,
        import_id=import_id,
        provenance=provenance,
    )


def test_job_completion_and_provenance_commit_with_dataset(tmp_path: Path) -> None:
    store = ImportStore(tmp_path)
    job = store.create_job("imported", {"source_code": "def process(row): pass"}, "key")
    job_id = str(job["id"])
    store.update_job(job_id, state="running", phase="processing")
    repository = DatasetRepository(tmp_path)
    provenance: dict[str, object] = {"source_code": "def process(row): pass", "import_id": job_id}
    with store.decision_lock():
        _publish(
            repository,
            dataset_id=str(job["candidate_dataset_id"]),
            import_id=job_id,
            provenance=provenance,
        )
    completed = store.get_job(job_id)
    record = repository.get("imported")
    assert completed["state"] == "succeeded"
    assert completed["dataset_id"] == record.id
    assert completed["rows_loaded"] == completed["rows_kept"] == 3
    assert repository.get_processor(record.id) == provenance
    assert record.snapshot_format_version == 2
    assert [len(example.tools) for example in repository.examples("imported")] == [1, 1, 0]
    assert store.request_cancel(job_id)["state"] == "succeeded"
    assert store.update_job(job_id, state="failed")["state"] == "succeeded"


def test_cancellation_rolls_back_dataset_provenance_and_job_completion(tmp_path: Path) -> None:
    store = ImportStore(tmp_path)
    job = store.create_job("imported", {}, "key")
    job_id = str(job["id"])
    store.update_job(job_id, state="running")
    store.request_cancel(job_id)
    repository = DatasetRepository(tmp_path)
    with store.decision_lock(), pytest.raises(ImportStateError):
        _publish(
            repository,
            dataset_id=str(job["candidate_dataset_id"]),
            import_id=job_id,
            provenance={"source_code": "processor"},
        )
    assert repository.list_datasets() == []
    assert store.get_job(job_id)["state"] == "cancelling"
    assert not list(tmp_path.rglob("*.parquet"))
    with sqlite3.connect(tmp_path / "catalog.sqlite") as connection:
        assert connection.execute("SELECT COUNT(*) FROM processor_provenance").fetchone() == (0,)


def test_idempotency_and_preview_survive_reopen_and_recovery(tmp_path: Path) -> None:
    store = ImportStore(tmp_path)
    expiry = datetime.now(UTC) + timedelta(hours=1)
    store.put_preview("preview", {"processor_contract_version": "2"}, expiry)
    first = store.create_job("imported", {"segment_keys": []}, "key")
    assert store.create_job("imported", {"segment_keys": []}, "key") == first
    with pytest.raises(IdempotencyConflictError):
        store.create_job("renamed", {"segment_keys": []}, "key")
    with pytest.raises(IdempotencyConflictError):
        store.create_job("imported", {"segment_keys": ["language"]}, "key")
    running = store.create_job("running", {}, "running")
    store.update_job(str(running["id"]), state="running", rows_loaded=5)
    reopened = ImportStore(tmp_path)
    assert reopened.get_preview("preview") == {
        "id": "preview",
        "spec": {"processor_contract_version": "2"},
        "expires_at": expiry.isoformat(),
    }
    assert reopened.get_preview("missing") is None
    assert reopened.recover_interrupted()[0]["state"] == "interrupted"
    assert reopened.get_job(str(first["id"]))["state"] == "queued"
    assert reopened.recover_interrupted() == []
    assert reopened.request_cancel(str(first["id"]))["state"] == "cancelled"
    with pytest.raises(KeyError):
        reopened.get_job("missing")


def test_concurrent_idempotent_submissions_create_one_job(tmp_path: Path) -> None:
    store = ImportStore(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: store.create_job("same", {}, "key"), range(8)))
    assert len({str(job["id"]) for job in jobs}) == 1
    assert len(store.list_jobs()) == 1


def test_publication_rejects_empty_results_without_files(tmp_path: Path) -> None:
    result = process_rows(iter([]), _processor, [])
    assert result.rows_loaded == result.rows_kept == result.rows_dropped == 0
    with pytest.raises(EmptyDatasetError):
        DatasetRepository(tmp_path).register_processed(
            "empty",
            result,
            SourceDescriptor(source_type="memory"),
            processor_id="test",
        )
    assert not list(tmp_path.rglob("*.parquet"))


def test_format_one_tools_segment_survives_migration_without_rewrite(tmp_path: Path) -> None:
    repository = DatasetRepository(tmp_path)
    _publish(repository)
    record = repository.get("imported")
    snapshot = tmp_path / record.parquet_path
    # Reconstruct a schema-v1 database and a legacy tools-named segment.
    pl.read_parquet(snapshot).with_columns(pl.lit("legacy segment").alias("tools")).write_parquet(
        snapshot
    )
    original = snapshot.read_bytes()
    with sqlite3.connect(tmp_path / "catalog.sqlite") as connection:
        connection.execute("UPDATE datasets SET segment_keys = ?", (json.dumps(["tools"]),))
        connection.execute("ALTER TABLE datasets DROP COLUMN snapshot_format_version")
        connection.execute("PRAGMA user_version = 1")
    migrated = DatasetRepository(tmp_path)
    assert migrated.get("imported").snapshot_format_version == 1
    assert snapshot.read_bytes() == original
    assert migrated.examples("imported")[0].segments == {"tools": "legacy segment"}
    assert migrated.examples("imported")[0].tools == []
    with pytest.raises(ValueError, match="reserved"):
        migrated.register_processed(
            "new",
            _result(),
            SourceDescriptor(source_type="memory"),
            processor_id="test",
            segments=["tools"],
        )


@pytest.mark.parametrize("corruption", ["missing", "null", "malformed", "future"])
def test_format_two_tools_corruption_is_not_silently_dropped(
    tmp_path: Path, corruption: str
) -> None:
    repository = DatasetRepository(tmp_path)
    _publish(repository)
    record = repository.get("imported")
    snapshot = tmp_path / record.parquet_path
    frame = pl.read_parquet(snapshot)
    if corruption == "missing":
        frame = frame.drop("tools")
    elif corruption == "future":
        with sqlite3.connect(tmp_path / "catalog.sqlite") as connection:
            connection.execute("UPDATE datasets SET snapshot_format_version = 99")
    else:
        frame = frame.with_columns(pl.lit("null" if corruption == "null" else "{}").alias("tools"))
    frame.write_parquet(snapshot)
    with pytest.raises((KeyError, ValueError)):
        repository.examples("imported")


def test_backup_and_seed_preserve_tools_versions_provenance_and_jobs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    store = ImportStore(source)
    job = store.create_job("imported", {"runtime_version": "1.3.0"}, "key")
    job_id = str(job["id"])
    store.update_job(job_id, state="running")
    repository = DatasetRepository(source)
    with store.decision_lock():
        _publish(
            repository,
            dataset_id=str(job["candidate_dataset_id"]),
            import_id=job_id,
            provenance={"import_id": job_id},
        )
    expected = [example.model_dump() for example in repository.examples("imported")]
    backup = tmp_path / "backup"
    backup_catalog(source, backup)
    seeded = tmp_path / "seeded"
    assert ensure_starter_catalog(seeded, backup)
    for root in (backup, seeded):
        copied = DatasetRepository(root)
        record = copied.get("imported")
        assert record.snapshot_format_version == 2
        assert [example.model_dump() for example in copied.examples("imported")] == expected
        assert copied.get_processor(record.id) == {"import_id": job_id}
        assert ImportStore(root).get_job(job_id)["state"] == "succeeded"


def test_publication_lock_serializes_a_racing_cancellation(tmp_path: Path) -> None:
    from threading import Event

    store = ImportStore(tmp_path)
    job = store.create_job("imported", {}, "key")
    job_id = str(job["id"])
    store.update_job(job_id, state="running")
    attempted = Event()

    def cancel() -> dict[str, object]:
        attempted.set()
        return store.request_cancel(job_id)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with store.decision_lock():
            pending = pool.submit(cancel)
            assert attempted.wait(timeout=3)
            assert not pending.done()
            _publish(
                DatasetRepository(tmp_path),
                dataset_id=str(job["candidate_dataset_id"]),
                import_id=job_id,
            )
        assert pending.result(timeout=3)["state"] == "succeeded"
    assert store.get_job(job_id)["state"] == "succeeded"


def test_python_registration_still_rejects_all_skipped_rows(tmp_path: Path) -> None:
    from tests.datasets.catalog.memory import MemorySource

    with pytest.raises(EmptyDatasetError):
        DatasetRepository(tmp_path).register(
            "empty",
            MemorySource(pl.DataFrame({"x": [1]})),
            lambda _: None,
            processor_id="tests.empty",
        )
    assert DatasetRepository(tmp_path).list_datasets() == []
    assert not list(tmp_path.rglob("*.parquet"))
