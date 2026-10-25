"""Row processing counts and segment checks."""

import polars as pl
import pytest

from llm_evaluation_hub.datasets.processing import (
    EmptyDatasetError,
    RowProcessingError,
    process_rows,
)
from llm_evaluation_hub.datasets.records import ProcessedExample


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "text": ["keep", "drop", "bad", "later"],
            "label": ["a", "b", "c", "d"],
            "language": ["tr", "en", "tr", "en"],
        }
    )


def _processor(row: dict[str, object]) -> ProcessedExample | None:
    text = row["text"]
    if text == "drop":
        return None
    if text == "bad":
        raise RuntimeError("bad row")
    label = row["label"]
    if not isinstance(label, str):
        raise TypeError("label must be a string")
    return ProcessedExample(
        conversation=[{"role": "user", "content": str(text)}],
        expected_output=label,
        segments={"language": str(row["language"])},
    )


def test_process_rows_counts_drops_and_keeps_source_index() -> None:
    frame = pl.DataFrame(
        {
            "text": ["keep", "drop", "later"],
            "label": ["a", "b", "d"],
            "language": ["tr", "en", "en"],
        }
    )

    result = process_rows(frame, _processor, ["language"])

    assert result.rows_loaded == 3
    assert result.rows_kept == 2
    assert result.rows_dropped == 1
    assert result.frame.get_column("source_index").to_list() == [0, 2]
    assert result.frame.get_column("language").to_list() == ["tr", "en"]


def test_process_rows_reports_the_source_index_when_the_processor_fails() -> None:
    with pytest.raises(RowProcessingError) as caught:
        process_rows(_frame(), _processor, ["language"])

    assert caught.value.source_index == 2


def test_process_rows_rejects_a_missing_or_extra_segment_key() -> None:
    frame = pl.DataFrame({"text": ["keep"], "label": ["a"], "language": ["tr"]})

    def missing(row: dict[str, object]) -> ProcessedExample:
        return ProcessedExample(
            conversation=[{"role": "user", "content": str(row["text"])}],
            segments={},
        )

    def extra(row: dict[str, object]) -> ProcessedExample:
        return ProcessedExample(
            conversation=[{"role": "user", "content": str(row["text"])}],
            segments={"language": "tr", "difficulty": "hard"},
        )

    with pytest.raises(RowProcessingError) as missing_error:
        process_rows(frame, missing, ["language"])
    with pytest.raises(RowProcessingError) as extra_error:
        process_rows(frame, extra, ["language"])

    assert missing_error.value.source_index == 0
    assert extra_error.value.source_index == 0


def test_process_rows_rejects_an_empty_result() -> None:
    frame = pl.DataFrame({"text": ["drop"], "label": ["a"], "language": ["tr"]})

    with pytest.raises(EmptyDatasetError):
        process_rows(frame, _processor, ["language"])


def test_blank_segment_value_is_kept() -> None:
    frame = pl.DataFrame({"text": ["keep"], "label": ["a"], "difficulty": [""]})

    def processor(row: dict[str, object]) -> ProcessedExample:
        return ProcessedExample(
            conversation=[{"role": "user", "content": str(row["text"])}],
            segments={"difficulty": str(row["difficulty"])},
        )

    result = process_rows(frame, processor, ["difficulty"])

    assert result.rows_kept == 1
    assert result.frame.get_column("difficulty").to_list() == [""]


def test_process_rows_without_segments_omits_segment_columns() -> None:
    frame = pl.DataFrame({"text": ["keep"], "label": ["a"]})

    def processor(row: dict[str, object]) -> ProcessedExample:
        label = row["label"]
        if not isinstance(label, str):
            raise TypeError("label must be a string")
        return ProcessedExample(
            conversation=[{"role": "user", "content": str(row["text"])}],
            expected_output=label,
        )

    result = process_rows(frame, processor, [])

    assert result.frame.columns == [
        "source_index",
        "conversation",
        "expected_output",
        "extras",
    ]
