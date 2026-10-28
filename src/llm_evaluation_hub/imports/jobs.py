"""Durable single-runner supervision and parent-only dataset publication."""

import fcntl
import json
import logging
import multiprocessing
import os
import shutil
import signal
import threading
import time
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import IO, cast
from uuid import UUID

import polars as pl

from llm_evaluation_hub.core.datasets.catalog import (
    DatasetRepository,
    DuplicateDatasetError,
    ImportStore,
    UnknownTagError,
)
from llm_evaluation_hub.core.datasets.processing import ProcessResult
from llm_evaluation_hub.core.datasets.sources import SourceDescriptor
from llm_evaluation_hub.imports.contracts import ImportSpec, JobView
from llm_evaluation_hub.imports.runtime import ProcessorError
from llm_evaluation_hub.imports.sources import HuggingFaceAdapter, SourceAdapter
from llm_evaluation_hub.imports.worker import diagnostic, validated_spec, worker_main

logger = logging.getLogger(__name__)
IMPORT_TIMEOUT = 600.0
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "interrupted"})


class OperationError(ProcessorError):
    """Preserve a child diagnostic with its source-row index."""

    def __init__(self, detail: dict[str, object]) -> None:
        """Copy the trusted child failure fields and row position."""
        super().__init__(
            cast(str, detail["category"]),
            cast(str, detail["message"]),
            line=cast(int | None, detail["line"]),
            column=cast(int | None, detail["column"]),
            field_path=cast(str | None, detail["field_path"]),
        )
        self.source_index = detail["source_index"]


def _wire(job: dict[str, object]) -> dict[str, object]:
    """Drop internal scheduler identities at the transport boundary."""
    return JobView.model_validate({key: job[key] for key in JobView.model_fields}).model_dump(
        mode="json"
    )


def _kill_group(process: BaseProcess) -> None:
    """Kill the whole isolated group, including children after its leader exits."""
    if process.pid is None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        # Startup cancellation may precede setsid in the new interpreter.
        if process.is_alive():
            process.kill()
    process.join(timeout=3)


class ImportSupervisor:
    """Own one durable import lane and one independent bounded preview lane."""

    def __init__(self, root: Path, source_adapter: SourceAdapter | None = None) -> None:
        """Configure trusted sources without starting threads or child processes."""
        self.root = Path(root)
        self.store = ImportStore(self.root)
        self.repository = DatasetRepository(self.root)
        self.adapter = source_adapter if source_adapter is not None else HuggingFaceAdapter()
        self._context = multiprocessing.get_context("spawn")
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._operations = threading.Semaphore(1)
        self._admission = threading.Lock()
        self._lock: IO[str] | None = None
        self._thread: threading.Thread | None = None
        self._children: set[BaseProcess] = set()
        self._children_lock = threading.Lock()

    def start(self) -> None:
        """Acquire catalog runner ownership, recover crashes, and dispatch queued jobs."""
        if self._thread is not None:
            return
        lock = (self.root / ".import-runner.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            lock.close()
            raise ProcessorError(
                "unavailable", "Another import runner owns this catalog."
            ) from error
        self._lock = lock
        self._stop.clear()
        try:
            recovered = self.store.recover_interrupted()
            for job in self.store.list_jobs():
                if job["state"] != "queued":
                    self._cleanup(job)
            self._thread = threading.Thread(target=self._run, name="dataset-imports", daemon=True)
            self._thread.start()
            logger.info("Import runner started; recovered=%d", len(recovered))
        except Exception:
            self._lock = None
            lock.close()
            raise

    def stop(self) -> None:
        """Stop active groups, preserve queued jobs, and release runner ownership."""
        self._stop.set()
        self._wake.set()
        with self._children_lock:
            children = list(self._children)
        for process in children:
            _kill_group(process)
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        # An operation can be unwinding its finally block after its group was killed.
        with self._operations:
            pass
        if self._lock is not None:
            self._lock.close()
            self._lock = None
        logger.info("Import runner stopped")

    def submit(
        self, name: str, spec: ImportSpec | dict[str, object], idempotency_key: str
    ) -> dict[str, object]:
        """Persist accepted immutable work, enforcing replay and queue admission."""
        checked = validated_spec(spec).model_dump(mode="json")
        with self._admission:
            # Replays remain accepted when the queue is full.
            jobs = self.store.list_jobs()
            replay = any(job["idempotency_key"] == idempotency_key for job in jobs)
            if not replay and sum(job["state"] == "queued" for job in jobs) >= 20:
                raise ProcessorError("busy", "The import queue is full.")
            if not replay:
                if any(dataset.name == name for dataset in self.repository.list_datasets()):
                    raise DuplicateDatasetError(name)
                known_tags = {tag.path for tag in self.repository.list_tags()}
                for tag in cast(list[str], checked["tags"]):
                    if tag not in known_tags:
                        raise UnknownTagError(tag)
            job = self.store.create_job(name, checked, idempotency_key)
        self._wake.set()
        return _wire(job)

    def get_job(self, id: str) -> dict[str, object]:
        """Read current durable state without waiting for heavy processing."""
        return _wire(self.store.get_job(id))

    def list_jobs(self) -> list[dict[str, object]]:
        """Rediscover durable history and queued work."""
        return [_wire(job) for job in self.store.list_jobs()]

    def cancel(self, id: str) -> dict[str, object]:
        """Arbitrate cancellation against publication and return acknowledged state."""
        job = self.store.request_cancel(id)
        self._wake.set()
        return _wire(job)

    def run_operation(
        self, kind: str, payload: dict[str, object], timeout: float = 30
    ) -> dict[str, object]:
        """Run a sample or preview with a deadline that includes waiting for its lane."""
        if kind not in {"sample", "preview"}:
            raise ValueError("Unknown interactive operation")
        deadline = time.monotonic() + timeout
        if not self._operations.acquire(timeout=max(0, timeout)):
            raise ProcessorError("timeout", "The operation deadline expired while waiting.")
        try:
            return self._execute(kind, payload, deadline)
        finally:
            self._operations.release()

    def _execute(
        self, kind: str, payload: dict[str, object], deadline: float, job_id: str | None = None
    ) -> dict[str, object]:
        """Poll an isolated process while keeping cancellation and shutdown responsive."""
        if self._stop.is_set() or time.monotonic() >= deadline:
            raise ProcessorError("timeout", "The operation is unavailable or its deadline expired.")
        receive, send = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=worker_main, args=(send, os.getpid(), kind, payload, self.adapter), daemon=False
        )
        try:
            # Serialize startup against stop's process snapshot.
            with self._children_lock:
                if self._stop.is_set():
                    raise ProcessorError("interrupted", "The application is shutting down.")
                process.start()
                self._children.add(process)
            send.close()
            return self._wait_child(process, receive, deadline, job_id)
        finally:
            if process.pid is not None:
                _kill_group(process)
            send.close()
            receive.close()
            with self._children_lock:
                self._children.discard(process)

    def _wait_child(
        self, process: BaseProcess, receive: object, deadline: float, job_id: str | None
    ) -> dict[str, object]:
        """Observe child results, throttled progress, and terminal interrupts."""
        from multiprocessing.connection import Connection

        pipe = cast(Connection, receive)
        last_progress = 0.0
        while True:
            self._check_interrupt(deadline, job_id)
            if pipe.poll(0.05):
                try:
                    message = pipe.recv()
                except EOFError as error:
                    raise ProcessorError(
                        "worker", "The isolated worker exited unexpectedly."
                    ) from error
                if "error" in message:
                    detail = message["error"]
                    error = OperationError(detail)
                    raise error
                # The child must exit before the parent can publish anything.
                while process.is_alive():
                    self._check_interrupt(deadline, job_id)
                    process.join(timeout=0.05)
                return message["result"]
            if not process.is_alive():
                raise ProcessorError("worker", "The isolated worker exited unexpectedly.")
            if job_id is not None and time.monotonic() - last_progress > 0.5:
                self._update_progress(job_id)
                last_progress = time.monotonic()

    def _check_interrupt(self, deadline: float, job_id: str | None) -> None:
        """Poll shutdown, cancellation and deadline even while a child is exiting."""
        if self._stop.is_set():
            raise ProcessorError("interrupted", "The application stopped during processing.")
        if job_id is not None and self.store.get_job(job_id)["state"] == "cancelling":
            raise ProcessorError("cancelled", "The import was cancelled.")
        if time.monotonic() >= deadline:
            raise ProcessorError("timeout", "The operation deadline expired.")

    def _update_progress(self, job_id: str) -> None:
        """Copy bounded counters from a child-owned atomic progress file."""
        path = self._staging(job_id) / "progress.json"
        try:
            progress = json.loads(path.read_text())
        except FileNotFoundError:
            return
        self.store.update_job(job_id, **progress)

    def _run(self) -> None:
        """Dispatch the oldest queued job, keeping unexpected faults observable."""
        while not self._stop.is_set():
            jobs = [job for job in reversed(self.store.list_jobs()) if job["state"] == "queued"]
            if jobs:
                self._run_job(jobs[0])
            else:
                self._wake.wait(0.25)
                self._wake.clear()

    def _run_job(self, job: dict[str, object]) -> None:
        """Stage child work, then arbitrate one atomic publication decision."""
        job_id = str(job["id"])
        try:
            with self.store.decision_lock():
                if self.store.get_job(job_id)["state"] != "queued" or self._stop.is_set():
                    return
                self.store.update_job(job_id, state="running", phase="processing")
            spec = validated_spec(cast(dict[str, object], job["spec"]))
            staging = self._staging(job_id)
            staging.mkdir(parents=True, exist_ok=False)
            logger.info("Import processing started; job=%s", job_id)
            counts = self._execute(
                "import",
                {"spec": spec.model_dump(mode="json"), "staging": str(staging)},
                time.monotonic() + IMPORT_TIMEOUT,
                job_id,
            )
            self.store.update_job(job_id, **counts)
            result = ProcessResult(
                pl.read_parquet(staging / "rows.parquet"),
                cast(int, counts["rows_loaded"]),
                cast(int, counts["rows_kept"]),
                cast(int, counts["rows_dropped"]),
            )
            with self.store.decision_lock():
                state = self.store.get_job(job_id)["state"]
                if state == "cancelling":
                    self.store.update_job(job_id, state="cancelled", phase="cancelled")
                    return
                if self._stop.is_set():
                    self.store.update_job(job_id, state="interrupted", phase="interrupted")
                    return
                self._publish(job, spec, result)
            logger.info("Import completed; job=%s kept=%d", job_id, result.rows_kept)
        except Exception as error:
            self._fail_job(job_id, error)
        finally:
            self._cleanup(job)

    def _publish(self, job: dict[str, object], spec: ImportSpec, result: ProcessResult) -> None:
        """Publish only finished staged data while holding the decision lock."""
        descriptor = SourceDescriptor(
            source_type=spec.source.kind,
            repo_id=spec.source.repo_id,
            config=spec.source.config,
            split=spec.source.split,
            revision=spec.source.revision,
            resolved_sha=spec.resolved_sha,
        )
        provenance = spec.model_dump(mode="json") | {"import_id": job["id"]}
        self.repository.register_processed(
            str(job["name"]),
            result,
            descriptor,
            processor_id=spec.source_hash,
            tags=spec.tags,
            segments=spec.segment_keys,
            limit=spec.row_limit,
            provenance=provenance,
            dataset_id=str(job["candidate_dataset_id"]),
            import_id=str(job["id"]),
        )

    def _fail_job(self, job_id: str, error: Exception) -> None:
        """Persist safe terminal failures without leaking row data or host paths."""
        detail = diagnostic(error)
        detail["source_index"] = getattr(error, "source_index", detail["source_index"])
        with self.store.decision_lock():
            state = self.store.get_job(job_id)["state"]
            if state in TERMINAL:
                return
            target = (
                "cancelled"
                if state == "cancelling"
                else ("interrupted" if self._stop.is_set() else "failed")
            )
            self.store.update_job(job_id, state=target, phase=target, error=detail)
        logger.warning(
            "Import stopped; job=%s state=%s category=%s", job_id, target, detail["category"]
        )

    def _staging(self, job_id: str) -> Path:
        """Construct only the fixed staging directory of a validated UUID."""
        return self.root / "tmp" / "imports" / str(UUID(job_id))

    def _cleanup(self, job: dict[str, object]) -> None:
        """Remove only known job staging and an unpublished candidate snapshot."""
        staging = self._staging(str(job["id"]))
        if staging.exists():
            shutil.rmtree(staging)
        current = self.store.get_job(str(job["id"]))
        if current["state"] != "succeeded":
            candidate = self.root / "datasets" / str(UUID(str(job["candidate_dataset_id"])))
            if candidate.exists():
                shutil.rmtree(candidate)
