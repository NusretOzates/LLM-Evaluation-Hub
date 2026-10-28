"""Bounded samples and processor previews, without catalog publication."""

from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Literal, Protocol
from uuid import uuid4

from llm_evaluation_hub.core.datasets.catalog import ImportStore
from llm_evaluation_hub.core.datasets.processing import RowProcessingError, require_segments
from llm_evaluation_hub.imports.contracts import (
    PROCESSOR_CONTRACT_VERSION,
    RUNTIME_POLICY_VERSION,
    Diagnostic,
    PreviewRequest,
    PreviewRow,
    PreviewView,
    SampleRequest,
    SampleView,
)
from llm_evaluation_hub.imports.runtime import ProcessorError, ProcessorRunner


class OperationRunner(Protocol):
    """Run bounded sample and processor work outside the HTTP process."""

    def run_operation(
        self, kind: Literal["sample", "preview"], payload: dict[str, object], *, timeout: float = 30
    ) -> dict[str, object]:
        """Return the worker's plain-JSON result before its deadline."""
        ...


class SampleLookupError(LookupError):
    """Distinguish an unknown sample from a known sample past its deadline."""

    def __init__(self, *, expired: bool, resource: str = "Source sample") -> None:
        """Record whether the requested cached sample is expired."""
        self.expired = expired
        super().__init__(f"{resource} expired." if expired else f"{resource} not found.")


def execute_preview(
    rows: list[dict[str, object]], source_code: str, segment_keys: list[str]
) -> dict[str, object]:
    """Run the real sandbox and retain safe per-row outcomes, including skips."""
    results: list[PreviewRow] = []
    kept, dropped = 0, 0
    with ProcessorRunner(source_code) as runner:
        source_hash, runtime_version = runner.source_hash, runner.runtime_version
        for index, row in enumerate(rows):
            try:
                example = runner.process(row)
                if example is None:
                    results.append(PreviewRow(source_index=index, status="skipped"))
                    dropped += 1
                else:
                    try:
                        require_segments(example, segment_keys, index)
                    except RowProcessingError as error:
                        raise ProcessorError(
                            "validation",
                            "Segment keys must match the declared keys.",
                            field_path="segments",
                        ) from error
                    results.append(PreviewRow(source_index=index, status="kept", example=example))
                    kept += 1
            except ProcessorError as error:
                results.append(
                    PreviewRow(
                        source_index=index,
                        status="failed",
                        error=Diagnostic(
                            category=error.category,
                            message=error.message,
                            source_index=index,
                            line=error.line,
                            column=error.column,
                            field_path=error.field_path,
                        ),
                    )
                )
    return {
        "source_hash": source_hash,
        "runtime_version": runtime_version,
        "rows": [row.model_dump(mode="json") for row in results],
        "rows_kept": kept,
        "rows_dropped": dropped,
        "valid": all(row.status != "failed" for row in results),
    }


class PreviewService:
    """Cache bounded source samples and persist successful execution attestations."""

    def __init__(self, store: ImportStore, supervisor: OperationRunner) -> None:
        """Bind persistence and process supervision without starting work."""
        self.store, self.supervisor = store, supervisor
        self.samples: OrderedDict[str, SampleView] = OrderedDict()
        self.lock = RLock()

    def sample(self, request: SampleRequest) -> SampleView:
        """Resolve and cache a transient sample pinned to an immutable commit."""
        result = self.supervisor.run_operation(
            "sample", request.model_dump(mode="json"), timeout=30
        )
        view = SampleView.model_validate(
            {
                **result,
                "id": str(uuid4()),
                "source": request.source,
                "row_limit": request.row_limit,
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            }
        )
        with self.lock:
            self.samples[view.id] = view
            while len(self.samples) > 10:
                self.samples.popitem(last=False)
        return view

    def preview(self, request: PreviewRequest) -> PreviewView:
        """Execute against cached rows and attest only entirely valid previews."""
        with self.lock:
            sample = self.samples.get(request.sample_id)
        if sample is None:
            raise SampleLookupError(expired=False)
        if sample.expires_at <= datetime.now(UTC):
            raise SampleLookupError(expired=True)
        result = self.supervisor.run_operation(
            "preview",
            {
                "rows": sample.rows,
                "source_code": request.source_code,
                "segment_keys": request.segment_keys,
            },
            timeout=30,
        )
        view = PreviewView.model_validate(
            {
                **{key: value for key, value in result.items() if key != "runtime_version"},
                "id": str(uuid4()) if result["valid"] else None,
                "sample_id": sample.id,
                "resolved_sha": sample.resolved_sha,
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            }
        )
        if view.id is not None:
            self.store.put_preview(
                view.id,
                {
                    "source": sample.source.model_dump(mode="json"),
                    "row_limit": sample.row_limit,
                    "resolved_sha": sample.resolved_sha,
                    "source_code": request.source_code,
                    "source_hash": view.source_hash,
                    "segment_keys": request.segment_keys,
                    "processor_contract_version": PROCESSOR_CONTRACT_VERSION,
                    "runtime_policy_version": RUNTIME_POLICY_VERSION,
                    "runtime_version": result["runtime_version"],
                },
                view.expires_at,
            )
        return view
