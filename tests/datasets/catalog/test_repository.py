"""Dataset registration and snapshot reads."""

import json
from pathlib import Path

import polars as pl
import pytest
from tests.datasets.catalog.memory import MemorySource

from llm_evaluation_hub.datasets.catalog import (
    DatasetRepository,
    DuplicateDatasetError,
    UnknownDatasetError,
    UnknownTagError,
)
from llm_evaluation_hub.datasets.processing import RowProcessingError
from llm_evaluation_hub.datasets.records import JsonValue, ProcessedExample


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
