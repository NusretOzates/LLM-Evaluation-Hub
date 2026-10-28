"""Dataset registration and snapshot reads."""

import json
import sqlite3
from pathlib import Path

import polars as pl
import pytest
from tests.datasets.catalog.memory import MemorySource

from llm_evaluation_hub.core.datasets.catalog import (
    DatasetRepository,
    DuplicateDatasetError,
    UnknownDatasetError,
    UnknownTagError,
)
from llm_evaluation_hub.core.datasets.processing import RowProcessingError
from llm_evaluation_hub.core.datasets.records import JsonValue, ProcessedExample


def _source() -> MemorySource:
    return MemorySource(
        pl.DataFrame(
            {
                "text": ["alpha", "beta", "gamma", ""],
                "label": ["refund", "unused", "unused", "other"],
                "language": ["tr", "en", "tr", "tr"],
                "difficulty": ["hard", "easy", "easy", ""],
            }
        )
    )


def _processor(row: dict[str, object]) -> ProcessedExample | None:
    text = str(row["text"])
    if text == "":
        return None
    expected: JsonValue
    if text == "beta":
        expected = {"label": "refund"}
    elif text == "gamma":
        expected = None
    else:
        label = row["label"]
        if not isinstance(label, str):
            raise TypeError("label must be a string")
        expected = label
    return ProcessedExample(
        conversation=[{"role": "user", "content": text}],
        expected_output=expected,
        extras={"rubric": "Use the policy."},
        segments={"language": str(row["language"]), "difficulty": str(row["difficulty"])},
    )


def _register(repository: DatasetRepository, name: str = "cases") -> MemorySource:
    repository.create_tag("Trendyol Cases")
    repository.create_tag("classification", parent="Trendyol Cases")
    source = _source()
    repository.register(
        name,
        source,
        _processor,
        processor_id="tests.cases",
        tags=["Trendyol Cases/classification"],
        segments=["language", "difficulty"],
    )
    return source


def test_register_stores_counts_segments_and_round_trips_examples(tmp_path: Path) -> None:
    repository = DatasetRepository(tmp_path / "catalog")
    _register(repository)

    record = repository.get("cases")
    frame = repository.rows("cases")
    examples = repository.examples("cases")

    assert record.created_at.tzinfo is not None
    assert record.rows_loaded == 4
    assert record.rows_kept == 3
    assert record.rows_dropped == 1
    assert record.segment_keys == ["language", "difficulty"]
    assert record.tags == ["Trendyol Cases/classification"]
    assert frame.get_column("source_index").to_list() == [0, 1, 2]
    assert frame.get_column("language").to_list() == ["tr", "en", "tr"]
    assert frame.columns == [
        "source_index",
        "conversation",
        "expected_output",
        "extras",
        "tools",
        "language",
        "difficulty",
    ]
    assert examples[0].conversation[0].content == ""
    assert examples[0].conversation[1].content == "alpha"
    assert examples[0].expected_output == "refund"
    assert examples[1].expected_output == {"label": "refund"}
    assert examples[2].expected_output is None
    assert examples[0].extras == {"rubric": "Use the policy."}
    assert json.loads(frame.get_column("expected_output")[0]) == "refund"


def test_examples_page_returns_the_requested_slice(tmp_path: Path) -> None:
    repository = DatasetRepository(tmp_path / "catalog")
    _register(repository)

    page = repository.examples("cases", offset=1, limit=1)
    assert [example.conversation[1].content for example in page] == ["beta"]
    assert repository.examples("cases", offset=10, limit=1) == []
    with pytest.raises(ValueError, match="offset"):
        repository.examples("cases", offset=-1)
    with pytest.raises(ValueError, match="limit"):
        repository.examples("cases", limit=0)


def test_register_without_segments_has_the_fixed_columns(tmp_path: Path) -> None:
    repository = DatasetRepository(tmp_path / "catalog")
    source = MemorySource(pl.DataFrame({"text": ["alpha"]}))

    def processor(row: dict[str, object]) -> ProcessedExample:
        return ProcessedExample(conversation=[{"role": "user", "content": str(row["text"])}])

    record = repository.register("plain", source, processor, processor_id="tests.plain")

    assert record.segment_keys == []
    assert repository.rows("plain").columns == [
        "source_index",
        "conversation",
        "expected_output",
        "extras",
        "tools",
    ]


def test_register_limit_is_stored_and_applied(tmp_path: Path) -> None:
    repository = DatasetRepository(tmp_path / "catalog")
    source = _source()

    record = repository.register(
        "sample",
        source,
        _processor,
        processor_id="tests.cases",
        segments=["language", "difficulty"],
        limit=1,
    )

    assert source.limit_seen == 1
    assert record.row_limit == 1
    assert record.rows_loaded == 1
    assert repository.rows("sample").height == 1


def test_failed_registration_leaves_no_dataset_or_parquet(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    repository = DatasetRepository(root)
    source = MemorySource(pl.DataFrame({"text": ["alpha", "beta"]}))

    def processor(row: dict[str, object]) -> ProcessedExample:
        if row["text"] == "beta":
            raise RuntimeError("bad row")
        return ProcessedExample(conversation=[{"role": "user", "content": str(row["text"])}])

    with pytest.raises(RowProcessingError) as caught:
        repository.register("broken", source, processor, processor_id="tests.broken")

    assert caught.value.source_index == 1
    with pytest.raises(UnknownDatasetError):
        repository.get("broken")
    assert list(root.rglob("*.parquet")) == []


def test_duplicate_name_keeps_the_first_snapshot(tmp_path: Path) -> None:
    repository = DatasetRepository(tmp_path / "catalog")
    _register(repository)
    source = MemorySource(pl.DataFrame({"text": ["other"]}))

    def processor(row: dict[str, object]) -> ProcessedExample:
        return ProcessedExample(conversation=[{"role": "user", "content": str(row["text"])}])

    with pytest.raises(DuplicateDatasetError):
        repository.register("cases", source, processor, processor_id="tests.other")

    assert repository.examples("cases")[0].conversation[1].content == "alpha"


def test_insert_failure_removes_the_parquet_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    repository = DatasetRepository(root)
    repository.create_tag("Trendyol Cases")
    source = MemorySource(pl.DataFrame({"text": ["alpha"]}))

    def processor(row: dict[str, object]) -> ProcessedExample:
        repository.delete_tag("Trendyol Cases")
        return ProcessedExample(conversation=[{"role": "user", "content": str(row["text"])}])

    with pytest.raises(UnknownTagError):
        repository.register(
            "cases",
            source,
            processor,
            processor_id="tests.cases",
            tags=["Trendyol Cases"],
        )

    with pytest.raises(UnknownDatasetError):
        repository.get("cases")
    assert list(root.rglob("*.parquet")) == []


def test_catalog_reopens_in_wal_mode(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    DatasetRepository(root)

    connection = sqlite3.connect(root / "catalog.sqlite")
    try:
        mode = connection.execute("PRAGMA journal_mode").fetchone()
    finally:
        connection.close()

    assert mode is not None
    assert mode[0] == "wal"


def test_unknown_tag_fails_before_a_snapshot_is_written(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    repository = DatasetRepository(root)

    with pytest.raises(UnknownTagError):
        repository.register(
            "cases",
            _source(),
            _processor,
            processor_id="tests.cases",
            tags=["Trendyol Cases"],
            segments=["language", "difficulty"],
        )

    assert list(root.rglob("*.parquet")) == []


def test_list_batches_tag_queries_and_reads_run_no_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = DatasetRepository(tmp_path / "catalog")
    repo.create_tag("Group")
    for index in range(12):
        repo.register(
            f"cases-{index}",
            _source(),
            _processor,
            processor_id="tests.batch",
            tags=["Group"],
            segments=["language", "difficulty"],
        )
    original_connect = sqlite3.connect
    statements: list[str] = []

    def traced_connect(database: str | Path) -> sqlite3.Connection:
        connection = original_connect(database)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(sqlite3, "connect", traced_connect)
    records = repo.list_datasets()
    assert len(records) == 12
    assert all(record.tags == ["Group"] for record in records)
    assert len([sql for sql in statements if sql.startswith("SELECT")]) == 2
    assert not any("CREATE TABLE" in sql or "journal_mode" in sql for sql in statements)


def test_storage_diagnostics_and_backup_restore(tmp_path: Path) -> None:
    from scripts.catalog_backup import backup_catalog

    root = tmp_path / "catalog"
    repo = DatasetRepository(root)
    _register(repo)
    record = repo.get("cases")
    (root / "unreferenced.parquet").write_bytes(b"orphan")
    assert repo.inspect_storage() == {"missing": [], "unreferenced": ["unreferenced.parquet"]}
    backup_catalog(root, tmp_path / "backup")
    backup_catalog(tmp_path / "backup", tmp_path / "restored")
    restored = DatasetRepository(tmp_path / "restored")
    assert restored.get("cases") == record
    assert restored.examples("cases") == repo.examples("cases")
    assert restored.inspect_storage() == {"missing": [], "unreferenced": []}
    (root / record.parquet_path).unlink()
    assert repo.inspect_storage()["missing"] == [record.parquet_path]
    with pytest.raises(FileExistsError):
        backup_catalog(root, tmp_path / "backup")


def test_future_schema_is_rejected_without_rewriting_version(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    DatasetRepository(root)
    with sqlite3.connect(root / "catalog.sqlite") as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="unsupported catalog schema"):
        DatasetRepository(root)
    with sqlite3.connect(root / "catalog.sqlite") as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 99


def test_killed_registration_is_reported_without_exposing_dataset(tmp_path: Path) -> None:
    import subprocess
    import sys

    root = tmp_path / "catalog"
    code = (
        "import os, sys, polars as pl; from pathlib import Path; "
        "from llm_evaluation_hub.core.datasets import DatasetRepository, ProcessedExample; "
        "from tests.datasets.catalog.memory import MemorySource; "
        "repo = DatasetRepository(Path(sys.argv[1])); "
        "repo._insert = lambda stored: os._exit(24); "
        "repo.register('killed', MemorySource(pl.DataFrame({'text': ['row']})), "
        "lambda row: ProcessedExample(conversation=[{'role': 'user', 'content': 'row'}]), "
        "processor_id='tests.kill')"
    )
    result = subprocess.run([sys.executable, "-c", code, str(root)], check=False, timeout=30)
    assert result.returncode == 24
    repo = DatasetRepository(root)
    assert repo.list_datasets() == []
    diagnostics = repo.inspect_storage()
    assert diagnostics["missing"] == []
    assert len(diagnostics["unreferenced"]) == 1
    assert (root / diagnostics["unreferenced"][0]).is_file()


def test_backup_rejects_parent_components_without_writing_outside_stage(tmp_path: Path) -> None:
    from scripts.catalog_backup import backup_catalog

    root = tmp_path / "catalog"
    repo = DatasetRepository(root)
    _register(repo)
    record = repo.get("cases")
    # This resolves within source but would escape a backup stage on another parent.
    with sqlite3.connect(root / "catalog.sqlite") as connection:
        connection.execute(
            "UPDATE datasets SET parquet_path = ?", (f"../catalog/{record.parquet_path}",)
        )
    backups = tmp_path / "backups"
    backups.mkdir()
    sentinel = backups / "catalog" / record.parquet_path
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"keep")
    with pytest.raises(ValueError, match="unsafe snapshot path"):
        backup_catalog(root, backups / "new")
    assert sentinel.read_bytes() == b"keep"
    assert not (backups / "new").exists()


def test_concurrent_registration_reports_duplicate_without_orphans(tmp_path: Path) -> None:
    import subprocess
    import sys

    root = tmp_path / "catalog"
    code = """
import sys
from pathlib import Path
import polars as pl
from tests.datasets.catalog.memory import MemorySource
from llm_evaluation_hub.core.datasets import DatasetRepository, ProcessedExample
from llm_evaluation_hub.core.datasets.catalog import DuplicateDatasetError
repo = DatasetRepository(Path(sys.argv[1]))
try:
    repo.register('same', MemorySource(pl.DataFrame({'text': ['row']})),
                  lambda row: ProcessedExample(conversation=[{'role': 'user', 'content': 'row'}]),
                  processor_id='tests.race')
    print('created')
except DuplicateDatasetError:
    print('duplicate')
"""
    processes = [
        subprocess.Popen([sys.executable, "-c", code, str(root)], stdout=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    outcomes = [process.communicate(timeout=30)[0].strip() for process in processes]
    assert all(process.returncode == 0 for process in processes)
    assert sorted(outcomes) == ["created", "duplicate"]
    repo = DatasetRepository(root)
    assert len(repo.list_datasets()) == 1
    assert repo.inspect_storage() == {"missing": [], "unreferenced": []}
