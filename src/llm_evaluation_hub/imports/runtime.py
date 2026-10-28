"""Execute dataset processors in the locked, capability-free Monty runtime."""

import base64
import hashlib
import json
import math
from datetime import UTC, datetime
from importlib.metadata import distribution, version
from pathlib import Path
from types import TracebackType
from typing import Literal, Self

from pydantic import ValidationError
from pydantic_monty import (
    Monty,
    MontyConversionError,
    MontyCrashedError,
    MontyRuntimeError,
    MontySyntaxError,
    OSPolicy,
    ResourceLimits,
)

from llm_evaluation_hub.core.datasets.records import ProcessedExample

MAX_SOURCE_BYTES = 65_536
MAX_ROW_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
RUNTIME_VERSION = "1.3.0"
_LIMITS: ResourceLimits = {
    "max_memory": 64 * 1024 * 1024,
    "max_feed_duration_secs": 0.25,
    "max_turn_duration_secs": 0.25,
    "max_recursion_depth": 100,
    "max_suspensions": 1000,
    "max_total_sleep_secs": 0,
}
_OS_POLICY: OSPolicy = {
    "datetime": datetime(2000, 1, 1, tzinfo=UTC),
    "timezone": "UTC",
    "random_start": {"seed": 0},
    "sleep": "zero",
    "process_time": "zero",
}


class ProcessorError(Exception):
    """Diagnostic-safe processor failure, without source rows or host details."""

    def __init__(
        self,
        category: str,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        field_path: str | None = None,
    ) -> None:
        """Initialize the public diagnostic fields."""
        super().__init__(message)
        self.category = category
        self.message = message
        self.line = line
        self.column = column
        self.field_path = field_path


def _bundled_binary() -> Path:
    """Resolve only the locked pure-runtime wheel, ignoring PATH and MONTY_BIN."""
    for package in ("pydantic-monty", "pydantic-monty-client", "pydantic-monty-runtime"):
        if version(package) != RUNTIME_VERSION:
            raise ProcessorError("unavailable", "The locked Monty runtime is unavailable.")
    runtime = distribution("pydantic-monty-runtime")
    for entry in runtime.files or ():
        if entry.name not in {"monty", "monty.exe"} or entry.hash is None:
            continue
        path = Path(str(runtime.locate_file(entry))).resolve()
        digest = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest())
        if entry.hash.mode == "sha256" and digest.rstrip(b"=").decode() == entry.hash.value:
            return path
    raise ProcessorError("unavailable", "The bundled Monty runtime failed integrity verification.")


def _field_path(parts: tuple[str | int, ...]) -> str | None:
    path = ""
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else part)
    return path or None


def validate_json_budget(value: object, *, category: str) -> int:
    """Validate finite JSON, depth and row size, returning its encoded UTF-8 bytes."""
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ProcessorError(category, "JSON nesting exceeds 64 levels.")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ProcessorError(category, "JSON object keys must be strings.")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ProcessorError(category, "JSON numbers must be finite.")
        elif item is not None and not isinstance(item, str | int | bool):
            raise ProcessorError(category, "Only JSON-compatible values are supported.")
    size = 0
    try:
        chunks = json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).iterencode(value)
        for chunk in chunks:
            size += len(chunk.encode("utf-8"))
            if size > MAX_ROW_BYTES:
                raise ProcessorError("resource_limit", "A processor input or output exceeds 1 MiB.")
    except (UnicodeError, ValueError) as error:
        raise ProcessorError(category, "Value cannot be encoded as finite UTF-8 JSON.") from error
    return size


def _discard_print(stream: Literal["stdout", "stderr"], text: str) -> None:
    """Discard sandbox output without logging potentially sensitive values."""
    del stream, text


def _execution_error(error: MontyRuntimeError | MontySyntaxError) -> ProcessorError:
    """Translate runtime failures without echoing user-raised values or paths."""
    frames = error.traceback()
    frame = frames[-1] if frames else None
    inner = error.exception()
    if isinstance(error, MontySyntaxError):
        category, message = "syntax", "Processor source contains invalid Python syntax."
    elif isinstance(inner, TimeoutError | MemoryError | RecursionError):
        category, message = "resource_limit", "Processor exceeded its execution resource limit."
    else:
        category, message = "runtime", f"Processor raised {type(inner).__name__}."
    return ProcessorError(
        category,
        message,
        line=frame.line if frame else None,
        column=frame.column if frame else None,
    )


class ProcessorRunner:
    """Own a Monty worker pool; execute each row in a completely fresh session."""

    runtime_version = RUNTIME_VERSION

    def __init__(self, source_code: str) -> None:
        """Bind immutable source and enforce the source size limit."""
        if len(source_code.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise ProcessorError("resource_limit", "Processor source exceeds 64 KiB.")
        self.source_hash = hashlib.sha256(source_code.encode("utf-8")).hexdigest()
        self._code = f"{source_code}\n\nprocess(row)"
        self._pool: Monty | None = None

    def __enter__(self) -> Self:
        """Start the verified, single-worker runtime pool."""
        if self._pool is not None:
            raise RuntimeError("ProcessorRunner is already open")
        try:
            self._pool = Monty(
                binary_path=_bundled_binary(),
                min_processes=1,
                max_processes=1,
                checkout_timeout=3,
                request_timeout=3,
                feed_duration_limit_grace=0.25,
                turn_duration_limit_grace=0.25,
            )
            self._pool.__enter__()
        except (OSError, LookupError, RuntimeError) as error:
            self._pool = None
            raise ProcessorError(
                "unavailable", "Unable to start the locked Monty runtime."
            ) from error
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop workers and release the owned pool."""
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.__exit__(exc_type, exc_value, traceback)

    def process(self, row: dict[str, object]) -> ProcessedExample | None:
        """Validate and process one JSON row, discarding the session even on failure."""
        if self._pool is None:
            raise RuntimeError("ProcessorRunner must be used as a context manager")
        if not isinstance(row, dict):
            raise ProcessorError("input", "Processor input must be a JSON object.")
        validate_json_budget(row, category="input")
        try:
            with self._pool.checkout(
                script_name="processor.py", limits=_LIMITS, os_policy=_OS_POLICY
            ) as session:
                output = session.feed_run(
                    self._code, inputs={"row": row}, print_callback=_discard_print
                )
        except (MontyRuntimeError, MontySyntaxError) as error:
            raise _execution_error(error) from None
        except MontyCrashedError:
            raise ProcessorError(
                "resource_limit", "Processor worker stopped or timed out."
            ) from None
        except MontyConversionError:
            raise ProcessorError("validation", "Processor returned an unsupported value.") from None
        if output is None:
            return None
        if not isinstance(output, dict):
            raise ProcessorError("validation", "Processor must return a dictionary or None.")
        validate_json_budget(output, category="validation")
        try:
            example = ProcessedExample.model_validate(output)
        except ValidationError as error:
            issue = error.errors(include_input=False, include_context=False, include_url=False)[0]
            raise ProcessorError(
                "validation",
                "Processor output does not match the example contract.",
                field_path=_field_path(issue["loc"]),
            ) from None
        validate_json_budget(example.model_dump(mode="json"), category="validation")
        return example
