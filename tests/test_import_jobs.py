"""Real-process supervision, publication and recovery tests."""

import hashlib
import json
import multiprocessing
import os
import signal
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from llm_evaluation_hub.api.app import create_app
from llm_evaluation_hub.core.datasets.catalog import ImportStore
from llm_evaluation_hub.core.datasets.processing import ProcessResult
from llm_evaluation_hub.imports.contracts import Diagnostic, ImportSpec, SourceSpec
from llm_evaluation_hub.imports.jobs import ImportSupervisor
from llm_evaluation_hub.imports.runtime import RUNTIME_VERSION, ProcessorError

CODE = (
    "def process(row):\n"
    '    return {"conversation": [{"role": "user", "content": row["text"]}], '
    '"tools": row.get("tools", [])}\n'
)


@dataclass
class SyntheticAdapter:
    delay: float = 0
    invalid_at: int | None = None
    marker: str | None = None

    def resolve(self, source: SourceSpec) -> str:
        return "abc123"

    def rows(
        self, source: SourceSpec, resolved_sha: str, limit: int
    ) -> Iterator[dict[str, object]]:
        assert resolved_sha == "abc123"
        if self.marker:
            child = subprocess.Popen(["sleep", "120"])
            Path(self.marker).write_text(
                json.dumps({"worker": os.getpid(), "descendant": child.pid})
            )
        for index in range(min(limit, 4)):
            time.sleep(self.delay)
            yield {"text": f"row {index}", "tools": None if index == self.invalid_at else []}


def spec(code: str = CODE, limit: int = 4) -> ImportSpec:
    return ImportSpec(
        source=SourceSpec(repo_id="synthetic/data"),
        row_limit=limit,
        resolved_sha="abc123",
        source_code=code,
        source_hash=hashlib.sha256(code.encode()).hexdigest(),
        segment_keys=[],
        runtime_version=RUNTIME_VERSION,
    )


def wait_state(
    supervisor: ImportSupervisor, job_id: str, states: set[str] | None = None
) -> dict[str, object]:
    target = states or {"succeeded", "failed", "cancelled", "interrupted"}
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = supervisor.get_job(job_id)
        if job["state"] in target:
            return job
        time.sleep(0.025)
    raise AssertionError(supervisor.get_job(job_id))


def wait_file(path: Path) -> dict[str, int]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text())
        time.sleep(0.025)
    raise AssertionError(f"Marker not created: {path}")


def assert_dead(pid: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        stat = Path(f"/proc/{pid}/stat")
        if not stat.exists() or stat.read_text().split()[2] == "Z":
            return
        time.sleep(0.025)
    raise AssertionError(f"Process remains alive: {pid}")


def test_success_atomic_replay_and_lifecycle(tmp_path: Path) -> None:
    app = create_app(tmp_path, source_adapter=SyntheticAdapter())
    with TestClient(app) as client:
        supervisor = app.state.import_supervisor
        accepted = supervisor.submit("imported", spec(), "once")
        job_id = accepted["id"]
        result = wait_state(supervisor, job_id)
        assert result["state"] == "succeeded", result
        assert result["rows_kept"] == 4
        dataset = supervisor.repository.get_by_id(result["dataset_id"])
        assert dataset.rows_loaded == 4
        assert supervisor.repository.get_processor(dataset.id)["import_id"] == job_id
        assert supervisor.submit("imported", spec(), "once")["id"] == job_id
        assert client.get("/dataset-imports/" + job_id).json()["state"] == "succeeded"
        assert supervisor.cancel(job_id)["state"] == "succeeded"
    assert not (tmp_path / "tmp" / "imports" / job_id).exists()


def test_late_invalid_row_has_safe_diagnostic_and_no_snapshot(tmp_path: Path) -> None:
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter(invalid_at=3))
    supervisor.start()
    try:
        job = supervisor.submit("bad", spec(), "bad")
        result = wait_state(supervisor, cast(str, job["id"]))
        assert result["state"] == "failed", result
        error = Diagnostic.model_validate(result["error"])
        assert error.source_index == 3
        assert error.field_path == "tools"
        assert supervisor.repository.list_datasets() == []
        assert not list((tmp_path / "datasets").glob("*/rows.parquet"))
    finally:
        supervisor.stop()


def test_cancellation_kills_descendants_and_reads_stay_responsive(tmp_path: Path) -> None:
    marker = tmp_path / "marker.json"
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter(delay=20, marker=str(marker)))
    supervisor.start()
    try:
        job = supervisor.submit("cancel", spec(), "cancel")
        pids = wait_file(marker)
        before = time.monotonic()
        assert supervisor.get_job(cast(str, job["id"]))["state"] == "running"
        assert time.monotonic() - before < 0.5
        supervisor.cancel(cast(str, job["id"]))
        assert wait_state(supervisor, cast(str, job["id"]))["state"] == "cancelled"
        assert_dead(pids["worker"])
        assert_dead(pids["descendant"])
        assert supervisor.repository.list_datasets() == []
    finally:
        supervisor.stop()


def test_restart_preserves_queued_and_interrupts_running(tmp_path: Path) -> None:
    store = ImportStore(tmp_path)
    active = store.create_job("prior", spec().model_dump(mode="json"), "prior")
    store.update_job(cast(str, active["id"]), state="running")
    queued = store.create_job("queued", spec().model_dump(mode="json"), "queued")
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter())
    supervisor.start()
    try:
        assert supervisor.get_job(cast(str, active["id"]))["state"] == "interrupted"
        assert wait_state(supervisor, cast(str, queued["id"]))["state"] == "succeeded"
    finally:
        supervisor.stop()


def test_shutdown_and_deadline_kill_groups(tmp_path: Path) -> None:
    marker = tmp_path / "shutdown.json"
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter(delay=20, marker=str(marker)))
    supervisor.start()
    job = supervisor.submit("shutdown", spec(), "shutdown")
    pids = wait_file(marker)
    supervisor.stop()
    assert supervisor.get_job(cast(str, job["id"]))["state"] == "interrupted"
    for pid in pids.values():
        assert_dead(pid)
    marker.unlink()
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter(delay=20, marker=str(marker)))
    with pytest.raises(ProcessorError, match="deadline"):
        supervisor.run_operation(
            "sample", {"source": spec().source.model_dump(), "row_limit": 4}, 2
        )
    pids = wait_file(marker)
    for pid in pids.values():
        assert_dead(pid)


def test_independent_preview_lane_and_timeout_while_waiting(tmp_path: Path) -> None:
    marker = tmp_path / "sample.json"
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter(delay=3, marker=str(marker)))
    failures = []

    def sample() -> None:
        try:
            supervisor.run_operation(
                "sample", {"source": spec().source.model_dump(), "row_limit": 4}, 3
            )
        except ProcessorError as error:
            failures.append(error.category)

    thread = threading.Thread(target=sample)
    thread.start()
    wait_file(marker)
    before = time.monotonic()
    with pytest.raises(ProcessorError, match="waiting"):
        supervisor.run_operation("preview", {}, 0.1)
    assert time.monotonic() - before < 0.5
    thread.join(5)
    assert failures == ["timeout"]
    assert supervisor.run_operation(
        "preview", {"rows": [{"text": "ready"}], "source_code": CODE, "segment_keys": []}
    )["valid"]


def _parent_lifetime(root: str, marker: str) -> None:
    supervisor = ImportSupervisor(Path(root), SyntheticAdapter(delay=30, marker=marker))
    supervisor.start()
    supervisor.submit("parent-death", spec(), "parent-death")
    time.sleep(120)


def test_parent_death_cleans_descendants(tmp_path: Path) -> None:
    marker = tmp_path / "parent.json"
    process = multiprocessing.get_context("spawn").Process(
        target=_parent_lifetime, args=(str(tmp_path), str(marker))
    )
    process.start()
    try:
        pids = wait_file(marker)
        assert process.pid is not None
        os.kill(process.pid, signal.SIGKILL)
        process.join(5)
        for pid in pids.values():
            assert_dead(pid)
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)


def test_single_runner_and_attestation_invalidation(tmp_path: Path) -> None:
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter())
    supervisor.start()
    try:
        other = ImportSupervisor(tmp_path, SyntheticAdapter())
        with pytest.raises(ProcessorError, match="Another"):
            other.start()
        with pytest.raises(ProcessorError, match="incompatible"):
            supervisor.submit("invalid", spec().model_copy(update={"source_hash": "bad"}), "bad")
    finally:
        supervisor.stop()


def test_import_lane_does_not_block_preview_and_zero_kept_fails(tmp_path: Path) -> None:
    marker = tmp_path / "active.json"
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter(delay=20, marker=str(marker)))
    supervisor.start()
    try:
        job = supervisor.submit("slow", spec(), "slow")
        wait_file(marker)
        result = supervisor.run_operation(
            "preview",
            {"rows": [{"text": "sample"}], "source_code": CODE, "segment_keys": []},
            timeout=5,
        )
        assert result["valid"] is True
        supervisor.cancel(cast(str, job["id"]))
        assert wait_state(supervisor, cast(str, job["id"]))["state"] == "cancelled"
    finally:
        supervisor.stop()
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter())
    supervisor.start()
    try:
        job = supervisor.submit("empty", spec("def process(row):\n    return None\n"), "empty")
        result = wait_state(supervisor, cast(str, job["id"]))
        assert result["state"] == "failed"
        error = Diagnostic.model_validate(result["error"])
        assert error.category == "validation"
        assert "kept zero rows" in error.message
        assert supervisor.repository.list_datasets() == []
    finally:
        supervisor.stop()


@pytest.mark.parametrize("publication_wins", [False, True])
def test_cancellation_publication_arbitration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, publication_wins: bool
) -> None:
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter())
    ready, release = threading.Event(), threading.Event()
    cancel_result = []
    if publication_wins:
        publish = supervisor._publish

        def paused_publish(
            job: dict[str, object], execution_spec: ImportSpec, result: ProcessResult
        ) -> None:
            ready.set()
            assert release.wait(5)
            publish(job, execution_spec, result)

        monkeypatch.setattr(supervisor, "_publish", paused_publish)
    else:
        execute = supervisor._execute

        def paused_execute(
            kind: str, payload: dict[str, object], deadline: float, job_id: str | None = None
        ) -> dict[str, object]:
            result = execute(kind, payload, deadline, job_id)
            ready.set()
            assert release.wait(5)
            return result

        monkeypatch.setattr(supervisor, "_execute", paused_execute)
    supervisor.start()
    try:
        job = supervisor.submit("race", spec(), "race")
        job_id = cast(str, job["id"])
        assert ready.wait(10)
        cancelling = threading.Thread(
            target=lambda: cancel_result.append(supervisor.cancel(job_id))
        )
        cancelling.start()
        if not publication_wins:
            cancelling.join(2)
            assert cancel_result[0]["state"] == "cancelling"
        release.set()
        cancelling.join(5)
        expected = "succeeded" if publication_wins else "cancelled"
        assert wait_state(supervisor, job_id)["state"] == expected
        assert bool(supervisor.repository.list_datasets()) is publication_wins
        assert cancel_result[0]["state"] == ("succeeded" if publication_wins else "cancelling")
    finally:
        release.set()
        supervisor.stop()


@pytest.mark.parametrize("direction", ["input", "output"])
def test_aggregate_limits_include_normalized_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direction: str
) -> None:
    from llm_evaluation_hub.core.datasets.processing import RowProcessingError
    from llm_evaluation_hub.imports import worker

    monkeypatch.setattr(worker, "MAX_AGGREGATE_BYTES", 60 if direction == "input" else 200)
    with pytest.raises((ProcessorError, RowProcessingError), match="exceeds 128 MiB"):
        worker.execute_import(
            SyntheticAdapter(), {"spec": spec().model_dump(mode="json"), "staging": str(tmp_path)}
        )
    assert not (tmp_path / "rows.parquet").exists()


def test_queue_admission_replay_and_queued_cancellation(tmp_path: Path) -> None:
    supervisor = ImportSupervisor(tmp_path, SyntheticAdapter())
    first = supervisor.submit("queued-0", spec(), "key-0")
    for index in range(1, 20):
        supervisor.submit(f"queued-{index}", spec(), f"key-{index}")
    assert supervisor.submit("queued-0", spec(), "key-0")["id"] == first["id"]
    with pytest.raises(ProcessorError, match="queue is full"):
        supervisor.submit("overflow", spec(), "overflow")
    assert supervisor.cancel(cast(str, first["id"]))["state"] == "cancelled"
    supervisor.submit("replacement", spec(), "replacement")
    with pytest.raises(ProcessorError, match="attestation is incompatible"):
        supervisor.submit(
            "invalid-policy",
            spec().model_copy(update={"runtime_policy_version": "99"}),
            "invalid-policy",
        )


def test_publication_conflict_diagnostics_are_actionable_without_echoing_names() -> None:
    from llm_evaluation_hub.core.datasets.catalog.errors import (
        DuplicateDatasetError,
        UnknownTagError,
    )
    from llm_evaluation_hub.imports.worker import diagnostic

    duplicate = Diagnostic.model_validate(diagnostic(DuplicateDatasetError("private dataset")))
    removed_tag = Diagnostic.model_validate(diagnostic(UnknownTagError("private tag")))
    assert duplicate.category == "conflict" and "already exists" in duplicate.message
    assert removed_tag.category == "validation" and "no longer exists" in removed_tag.message
    assert "private" not in duplicate.message and "private" not in removed_tag.message
