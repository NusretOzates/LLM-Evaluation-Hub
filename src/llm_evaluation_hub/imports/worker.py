"""Isolated process entry points for bounded source and import work."""

import ctypes
import hashlib
import json
import os
import signal
from collections.abc import Iterator
from itertools import islice
from multiprocessing.connection import Connection
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from llm_evaluation_hub.core.datasets.catalog.errors import DuplicateDatasetError, UnknownTagError
from llm_evaluation_hub.core.datasets.processing import (
    EmptyDatasetError,
    RowProcessingError,
    process_rows,
    validate_segment_declaration,
)
from llm_evaluation_hub.core.datasets.records import ProcessedExample
from llm_evaluation_hub.imports.contracts import (
    PROCESSOR_CONTRACT_VERSION,
    RUNTIME_POLICY_VERSION,
    Diagnostic,
    ImportSpec,
    SampleRequest,
)
from llm_evaluation_hub.imports.runtime import (
    RUNTIME_VERSION,
    ProcessorError,
    ProcessorRunner,
    validate_json_budget,
)
from llm_evaluation_hub.imports.sources import SourceAdapter

MAX_AGGREGATE_BYTES = 128 * 1024 * 1024


def isolate_process(parent_pid: int) -> None:
    """Create an owned process group and kill it if the supervising parent dies."""
    os.setsid()

    def parent_died(signum: int, frame: object) -> None:
        del signum, frame
        os.killpg(os.getpid(), signal.SIGKILL)

    signal.signal(signal.SIGTERM, parent_died)
    # Linux sends this signal even when the parent exits without normal cleanup.
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError("Unable to install parent death protection")
    if os.getppid() != parent_pid:
        parent_died(signal.SIGTERM, None)


def diagnostic(error: Exception) -> dict[str, object]:
    """Convert only known safe failures into transport diagnostics."""
    if isinstance(error, EmptyDatasetError):
        return Diagnostic(
            category="validation", message="The processor kept zero rows."
        ).model_dump()
    index = None
    if isinstance(error, RowProcessingError):
        index = error.source_index
        cause = error.__cause__
        if isinstance(cause, ProcessorError):
            error = cause
        else:
            return Diagnostic(
                category="validation",
                message="The source row failed validation.",
                source_index=index,
                field_path="segments",
            ).model_dump()
    if isinstance(error, (DuplicateDatasetError, UnknownTagError)):
        category, message = (
            ("conflict", "A dataset with this name already exists.")
            if isinstance(error, DuplicateDatasetError)
            else ("validation", "An import tag no longer exists.")
        )
        return Diagnostic(category=category, message=message).model_dump()
    if isinstance(error, ProcessorError):
        return Diagnostic(
            category=error.category,
            message=error.message,
            source_index=index,
            line=error.line,
            column=error.column,
            field_path=error.field_path,
        ).model_dump()
    return Diagnostic(category="internal", message="The isolated operation failed.").model_dump()


def validated_spec(value: object) -> ImportSpec:
    """Reject incompatible attestations before accepting or executing work."""
    try:
        raw = value.model_dump(mode="json") if isinstance(value, ImportSpec) else value
        spec = ImportSpec.model_validate(raw)
        validate_segment_declaration(spec.segment_keys)
    except (ValidationError, ValueError) as error:
        raise ProcessorError("validation", "The import specification is invalid.") from error
    digest = hashlib.sha256(spec.source_code.encode("utf-8")).hexdigest()
    if (
        spec.source_hash != digest
        or spec.runtime_version != RUNTIME_VERSION
        or spec.processor_contract_version != PROCESSOR_CONTRACT_VERSION
        or spec.runtime_policy_version != RUNTIME_POLICY_VERSION
    ):
        raise ProcessorError(
            "validation", "The processor attestation is incompatible; preview again."
        )
    if not spec.resolved_sha or len(spec.source_code.encode("utf-8")) > 65_536:
        raise ProcessorError("validation", "The processor specification exceeds policy limits.")
    return spec


def execute_import(adapter: SourceAdapter, payload: dict[str, object]) -> dict[str, object]:
    """Stream pinned rows through Monty and stage one complete processed frame."""
    spec = validated_spec(payload["spec"])
    staging = Path(str(payload["staging"]))
    input_bytes = output_bytes = loaded = kept = dropped = 0

    def progress() -> None:
        temporary = staging / "progress.pending"
        temporary.write_text(
            json.dumps({"rows_loaded": loaded, "rows_kept": kept, "rows_dropped": dropped})
        )
        temporary.replace(staging / "progress.json")

    def rows() -> Iterator[dict[str, object]]:
        nonlocal input_bytes
        stream = adapter.rows(spec.source, spec.resolved_sha, spec.row_limit)
        for row in islice(stream, spec.row_limit):
            input_bytes += validate_json_budget(row, category="source")
            if input_bytes > MAX_AGGREGATE_BYTES:
                raise ProcessorError("resource_limit", "Imported input exceeds 128 MiB.")
            yield row

    with ProcessorRunner(spec.source_code) as runner:

        def process(row: dict[str, object]) -> ProcessedExample | None:
            nonlocal output_bytes, loaded, kept, dropped
            example = runner.process(row)
            loaded += 1
            if example is None:
                dropped += 1
            else:
                output_bytes += validate_json_budget(
                    example.model_dump(mode="json"), category="validation"
                )
                if output_bytes > MAX_AGGREGATE_BYTES:
                    raise ProcessorError("resource_limit", "Imported output exceeds 128 MiB.")
                kept += 1
            if loaded % 25 == 0:
                progress()
            return example

        result = process_rows(rows(), process, spec.segment_keys)
    progress()
    result.frame.write_parquet(staging / "rows.parquet")
    return {
        "rows_loaded": result.rows_loaded,
        "rows_kept": result.rows_kept,
        "rows_dropped": result.rows_dropped,
    }


def worker_main(
    connection: Connection,
    parent_pid: int,
    kind: str,
    payload: dict[str, object],
    adapter: SourceAdapter,
) -> None:
    """Dispatch trusted operations and emit a bounded result or safe diagnostic."""
    try:
        isolate_process(parent_pid)
        if kind == "import":
            result = execute_import(adapter, payload)
        elif kind == "sample":
            from llm_evaluation_hub.imports.sources import collect_sample

            request = SampleRequest.model_validate(payload)
            result = collect_sample(adapter, request.source, request.row_limit)
        elif kind == "preview":
            from llm_evaluation_hub.imports.previews import execute_preview

            result = execute_preview(
                cast(list[dict[str, object]], payload["rows"]),
                cast(str, payload["source_code"]),
                cast(list[str], payload["segment_keys"]),
            )
        else:
            raise ValueError("Unknown operation")
        connection.send({"result": result})
    except Exception as error:
        connection.send({"error": diagnostic(error)})
    finally:
        connection.close()
