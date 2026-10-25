"""Starter catalog publication across restarts and interrupted copies."""

import sqlite3
from pathlib import Path

import pytest

from llm_evaluation_hub.api.asgi import app
from llm_evaluation_hub.api.seed import ensure_starter_catalog


def _seed(root: Path) -> Path:
    root.mkdir()
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
    assert (catalog / "datasets" / "rows.bin").read_text() == "payload"


def test_incomplete_copy_is_replaced(tmp_path: Path) -> None:
    seed = _seed(tmp_path / "seed")
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "datasets").mkdir()
    (catalog / "datasets" / "stale.bin").write_text("stale")
    (catalog / ".catalog.sqlite.partial").write_bytes(b"partial")

    assert ensure_starter_catalog(catalog, seed)

    assert _marker(catalog) == "seed"
    assert not (catalog / "datasets" / "stale.bin").exists()
    assert not (catalog / ".catalog.sqlite.partial").exists()
    assert (catalog / "datasets" / "rows.bin").read_text() == "payload"


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

    assert not (tmp_path / "catalog").exists()


def test_factory_skips_an_unset_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(tmp_path / "seed")
    catalog = tmp_path / "catalog"
    monkeypatch.setenv("LLM_EVAL_CATALOG", str(catalog))
    monkeypatch.delenv("LLM_EVAL_SEED", raising=False)

    app()

    assert not (catalog / "datasets" / "rows.bin").exists()


def test_factory_skips_a_blank_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(tmp_path / "seed")
    catalog = tmp_path / "catalog"
    monkeypatch.setenv("LLM_EVAL_CATALOG", str(catalog))
    monkeypatch.setenv("LLM_EVAL_SEED", "  ")

    app()

    assert not (catalog / "datasets" / "rows.bin").exists()


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
