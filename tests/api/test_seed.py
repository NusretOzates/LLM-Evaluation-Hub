"""Starter catalog publication across restarts and interrupted copies."""

import sqlite3
from pathlib import Path

import pytest

from llm_evaluation_hub.api.asgi import app
from llm_evaluation_hub.api.seed import ensure_starter_catalog
from llm_evaluation_hub.core.datasets.catalog import DatasetRepository


def _seed(root: Path) -> Path:
    root.mkdir()
    DatasetRepository(root)
    database = sqlite3.connect(root / "catalog.sqlite")
    try:
        database.execute("CREATE TABLE marker (value TEXT)")
        database.execute("INSERT INTO marker (value) VALUES ('seed')")
        database.commit()
    finally:
        database.close()
    payload = root / "datasets"
    payload.mkdir()
    (payload / "rows.bin").write_text("payload")
    return root


def _marker(catalog: Path) -> str:
    connection = sqlite3.connect(catalog / "catalog.sqlite")
    try:
        row = connection.execute("SELECT value FROM marker").fetchone()
    finally:
        connection.close()
    assert row is not None
    return str(row[0])


def test_existing_catalog_survives_a_second_publish(tmp_path: Path) -> None:
    seed = _seed(tmp_path / "seed")
    catalog = tmp_path / "catalog"

    assert ensure_starter_catalog(catalog, seed)
    connection = sqlite3.connect(catalog / "catalog.sqlite")
    try:
        connection.execute("UPDATE marker SET value = 'user'")
        connection.commit()
    finally:
        connection.close()
    (catalog / "note.txt").write_text("keep")

    assert not ensure_starter_catalog(catalog, seed)
    assert _marker(catalog) == "user"
    assert (catalog / "note.txt").read_text() == "keep"
    assert (catalog / ".starter" / "datasets" / "rows.bin").read_text() == "payload"


def test_unknown_target_content_is_preserved(tmp_path: Path) -> None:
    seed = _seed(tmp_path / "seed")
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    note = catalog / "note.txt"
    note.write_text("keep")
    with pytest.raises(RuntimeError, match="nonempty"):
        ensure_starter_catalog(catalog, seed)
    assert note.read_text() == "keep"
    assert not (catalog / "catalog.sqlite").exists()


def test_invalid_seed_leaves_the_target_untouched(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "catalog.sqlite").write_text("not a database")
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "keep.txt").write_text("keep")

    with pytest.raises(sqlite3.DatabaseError):
        ensure_starter_catalog(catalog, seed)

    assert (catalog / "keep.txt").read_text() == "keep"
    assert not (catalog / "catalog.sqlite").exists()


def test_missing_seed_database_raises_before_creating_the_catalog(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()

    with pytest.raises(FileNotFoundError):
        ensure_starter_catalog(tmp_path / "catalog", seed)

    assert not (tmp_path / "catalog" / "catalog.sqlite").exists()


def test_factory_skips_an_unset_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(tmp_path / "seed")
    catalog = tmp_path / "catalog"
    monkeypatch.setenv("LLM_EVAL_CATALOG", str(catalog))
    monkeypatch.delenv("LLM_EVAL_SEED", raising=False)

    app()

    assert not (catalog / ".starter" / "datasets" / "rows.bin").exists()


def test_factory_skips_a_blank_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(tmp_path / "seed")
    catalog = tmp_path / "catalog"
    monkeypatch.setenv("LLM_EVAL_CATALOG", str(catalog))
    monkeypatch.setenv("LLM_EVAL_SEED", "  ")

    app()

    assert not (catalog / ".starter" / "datasets" / "rows.bin").exists()


def test_factory_publishes_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed = _seed(tmp_path / "seed")
    catalog = tmp_path / "catalog"
    monkeypatch.setenv("LLM_EVAL_CATALOG", str(catalog))
    monkeypatch.setenv("LLM_EVAL_SEED", str(seed))

    app()
    connection = sqlite3.connect(catalog / "catalog.sqlite")
    try:
        connection.execute("UPDATE marker SET value = 'user'")
        connection.commit()
    finally:
        connection.close()
    app()

    assert _marker(catalog) == "user"


def test_overlapping_paths_are_rejected(tmp_path: Path) -> None:
    seed = _seed(tmp_path / "seed")
    for target in (seed, seed / "child", tmp_path):
        with pytest.raises(ValueError, match="overlap"):
            ensure_starter_catalog(target, seed)
    assert _marker(seed) == "seed"


def test_two_processes_publish_only_once(tmp_path: Path) -> None:
    import subprocess
    import sys

    seed = _seed(tmp_path / "seed")
    target = tmp_path / "catalog"
    code = (
        "from pathlib import Path; import sys; "
        "from llm_evaluation_hub.api.seed import ensure_starter_catalog; "
        "print(ensure_starter_catalog(Path(sys.argv[1]), Path(sys.argv[2])))"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(target), str(seed)], stdout=subprocess.PIPE, text=True
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=30)[0].strip() for process in processes]
    assert all(process.returncode == 0 for process in processes)
    assert sorted(results) == ["False", "True"]
    assert _marker(target) == "seed"


def test_process_death_before_database_publish_can_resume(tmp_path: Path) -> None:
    import subprocess
    import sys

    seed = _seed(tmp_path / "seed")
    target = tmp_path / "catalog"
    code = (
        "import os, sys; from pathlib import Path; "
        "import llm_evaluation_hub.api.seed as s; "
        "s._require_snapshots = lambda *args: os._exit(23); "
        "s.ensure_starter_catalog(Path(sys.argv[1]), Path(sys.argv[2]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(target), str(seed)], check=False, timeout=30
    )
    assert result.returncode == 23
    assert not (target / "catalog.sqlite").exists()
    from llm_evaluation_hub.core.datasets import DatasetRepository

    with pytest.raises(RuntimeError, match="pending starter publication"):
        DatasetRepository(target)
    assert not (target / "catalog.sqlite").exists()
    assert ensure_starter_catalog(target, seed)
    assert _marker(target) == "seed"


def test_seeded_repository_round_trips_snapshots_and_rejects_missing_payload(
    tmp_path: Path,
) -> None:
    import polars as pl
    from tests.datasets.catalog.memory import MemorySource

    from llm_evaluation_hub.core.datasets import DatasetRepository, ProcessedExample

    seed = tmp_path / "seed"
    repo = DatasetRepository(seed)
    record = repo.register(
        "snapshot",
        MemorySource(pl.DataFrame({"text": ["kept"]})),
        lambda row: ProcessedExample(conversation=[{"role": "user", "content": str(row["text"])}]),
        processor_id="tests.seed",
    )
    target = tmp_path / "target"
    assert ensure_starter_catalog(target, seed)
    restored = DatasetRepository(target)
    assert restored.examples("snapshot") == repo.examples("snapshot")
    assert restored.inspect_storage() == {"missing": [], "unreferenced": []}
    (seed / record.parquet_path).unlink()
    with pytest.raises(RuntimeError, match="missing or unsafe"):
        ensure_starter_catalog(tmp_path / "bad-target", seed)
    assert not (tmp_path / "bad-target" / "catalog.sqlite").exists()


def test_process_death_during_staging_leaves_owned_files_for_inspection(tmp_path: Path) -> None:
    import subprocess
    import sys

    seed = _seed(tmp_path / "seed")
    target = tmp_path / "catalog"
    code = (
        "import os, sys; from pathlib import Path; "
        "import llm_evaluation_hub.api.seed as s; "
        "s._backup_sqlite = lambda *args: os._exit(25); "
        "s.ensure_starter_catalog(Path(sys.argv[1]), Path(sys.argv[2]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(target), str(seed)], check=False, timeout=30
    )
    assert result.returncode == 25
    interrupted = list(target.glob(".seed-stage-*"))
    assert len(interrupted) == 1
    assert ensure_starter_catalog(target, seed)
    assert interrupted[0].is_dir()
    assert _marker(target) == "seed"
