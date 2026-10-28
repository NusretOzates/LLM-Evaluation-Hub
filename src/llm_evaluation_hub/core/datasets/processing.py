"""Apply a row processor and build the stored Polars frame."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import polars as pl
from pydantic import ValidationError

from llm_evaluation_hub.core.datasets.records import (
    ProcessedExample,
    dump_json,
    encode_conversation,
    encode_expected_output,
    encode_extras,
    validate_segment_key,
)


class RowProcessingError(Exception):
    """The processor failed or returned an invalid example for one source row."""

    def __init__(self, source_index: int, reason: str) -> None:
        """Record the source row that failed."""
        self.source_index = source_index
        super().__init__(f"row {source_index} failed: {reason}")


class EmptyDatasetError(Exception):
    """Registration kept zero rows."""

    def __init__(self) -> None:
        """Explain that an empty snapshot is not stored."""
        super().__init__("processor kept zero rows")


RowProcessor = Callable[[dict[str, object]], ProcessedExample | None]


@dataclass(frozen=True)
class ProcessResult:
    """Counts and the frame that registration stores."""

    frame: pl.DataFrame
    rows_loaded: int
    rows_kept: int
    rows_dropped: int


def validate_segment_declaration(keys: Sequence[str]) -> list[str]:
    """Return the segment columns in declaration order."""
    ordered = list(keys)
    if len(set(ordered)) != len(ordered):
        raise ValueError("segment keys must be unique")
    for key in ordered:
        validate_segment_key(key)
        if key == "tools":
            raise ValueError("tools is reserved for available tool definitions")
    return ordered


def process_rows(
    rows: Iterable[dict[str, object]],
    processor: RowProcessor,
    segment_keys: Sequence[str],
) -> ProcessResult:
    """Process each source row. A `None` return drops that row."""
    declared = validate_segment_declaration(segment_keys)
    stored: list[dict[str, object]] = []
    dropped = 0
    rows_loaded = 0
    for source_index, row in enumerate(rows):
        rows_loaded += 1
        example = _call_processor(processor, source_index, dict(row))
        if example is None:
            dropped += 1
            continue
        require_segments(example, declared, source_index)
        stored.append(_stored_row(example, source_index, declared))
    return ProcessResult(
        frame=_frame(stored, declared),
        rows_loaded=rows_loaded,
        rows_kept=len(stored),
        rows_dropped=dropped,
    )


def _call_processor(
    processor: RowProcessor,
    source_index: int,
    row: dict[str, object],
) -> ProcessedExample | None:
    """Run the processor and attach the source index to any failure."""
    try:
        example = processor(row)
    except ValidationError as error:
        raise RowProcessingError(source_index, str(error)) from error
    except RowProcessingError:
        raise
    except Exception as error:
        raise RowProcessingError(source_index, str(error)) from error
    if example is not None and not isinstance(example, ProcessedExample):
        raise RowProcessingError(source_index, "processor must return ProcessedExample or None")
    return example


def require_segments(
    example: ProcessedExample,
    segment_keys: list[str],
    source_index: int,
) -> None:
    """Require the example to carry exactly the declared segment keys."""
    if set(example.segments) != set(segment_keys):
        raise RowProcessingError(
            source_index,
            "segment keys must match the keys declared at registration",
        )


def _stored_row(
    example: ProcessedExample,
    source_index: int,
    segment_keys: list[str],
) -> dict[str, object]:
    """Map one example onto the Parquet column layout."""
    row: dict[str, object] = {
        "source_index": source_index,
        "conversation": encode_conversation(example.conversation),
        "expected_output": encode_expected_output(example.expected_output),
        "extras": encode_extras(example.extras),
        "tools": dump_json(
            [tool.model_dump(mode="json", exclude_none=True) for tool in example.tools]
        ),
    }
    for key in segment_keys:
        row[key] = example.segments[key]
    return row


def _frame(rows: list[dict[str, object]], segment_keys: list[str]) -> pl.DataFrame:
    """Build the stored frame with an explicit schema."""
    schema: dict[str, pl.DataType] = {
        "source_index": pl.Int64(),
        "conversation": pl.Utf8(),
        "expected_output": pl.Utf8(),
        "extras": pl.Utf8(),
        "tools": pl.Utf8(),
    }
    for key in segment_keys:
        schema[key] = pl.Utf8()
    return pl.DataFrame(rows, schema=schema)
