"""Single active asynchronous runner with durable per-row results."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import threading
import time
from collections import deque
from typing import Any

from openai import AsyncOpenAI

from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection
from llm_evaluation_hub.inference.compiler import compile_request
from llm_evaluation_hub.inference.contracts import (
    ConnectionProfile,
    OutputFormat,
    RowResult,
    RunSpec,
)
from llm_evaluation_hub.inference.store import InferenceStore, now
from llm_evaluation_hub.inference.transport import AuthenticationFailure, send


class Runner:
    """Run queued work in one background event loop, requiring explicit recovery."""

    def __init__(self, store: InferenceStore) -> None:
        """Bind a runner to one catalog."""
        self.store = store
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.task: asyncio.Task[None] | None = None
        self.active_id: str | None = None
        self.ready = threading.Event()
        self.stopping = False
        self.admission = threading.Lock()
        self.lock_file = None

    def start(self) -> None:
        """Mark unfinished work interrupted, then start dispatch."""
        self.lock_file = (self.store.root / ".inference.lock").open("a")
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            self.lock_file = None
            raise RuntimeError("another inference runner owns this catalog") from None
        with catalog_connection(self.store.root) as db:
            db.execute(
                "UPDATE inference_runs SET state = CASE WHEN state = "
                "'canceling' THEN 'canceled' ELSE 'interrupted' END, updated_at = ? WHERE "
                "state IN ('running', 'queued', 'canceling')",
                (now(),),
            )
        self.thread = threading.Thread(target=self._thread, daemon=True)
        self.thread.start()
        self.ready.wait()

    def _thread(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            asyncio.run(self._loop())

    async def _loop(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.ready.set()
        while True:
            with catalog_connection(self.store.root) as db:
                row = db.execute(
                    "SELECT id FROM inference_runs WHERE state = 'queued' "
                    "ORDER BY created_at LIMIT 1"
                ).fetchone()
            if row is None:
                await asyncio.sleep(0.1)
                continue
            if not self.admission.acquire(blocking=False):
                await asyncio.sleep(0.1)
                continue
            self.active_id = row[0]
            self.task = asyncio.create_task(self._execute(row[0]))
            try:
                await self.task
            except asyncio.CancelledError:
                if self.stopping:
                    raise
            except Exception:
                with catalog_connection(self.store.root) as db:
                    db.execute(
                        "UPDATE inference_runs SET state = 'interrupted', "
                        "error = 'inference execution failed', updated_at = ? WHERE id = ? "
                        "AND state = 'running'",
                        (now(), row[0]),
                    )
            finally:
                with catalog_connection(self.store.root) as db:
                    db.execute(
                        "UPDATE inference_runs SET state = 'canceled', "
                        "updated_at = ? WHERE id = ? AND state = 'canceling'",
                        (now(), row[0]),
                    )
                self.task = None
                self.active_id = None
                self.admission.release()

    def stop(self) -> None:
        """Stop active requests without automatically resuming them later."""
        if self.loop:
            self.loop.call_soon_threadsafe(self._shutdown)
        if self.thread:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise RuntimeError("inference runner did not stop")
        if self.lock_file:
            self.lock_file.close()
            self.lock_file = None

    def _shutdown(self) -> None:
        self.stopping = True
        for task in asyncio.all_tasks():
            task.cancel()

    def cancel(self, run_id: str) -> None:
        """Cancel queued or active work and preserve committed results."""
        with catalog_connection(self.store.root) as db:
            db.execute(
                "UPDATE inference_runs SET state = CASE WHEN state = "
                "'running' THEN 'canceling' ELSE 'canceled' END, updated_at = ? WHERE id = "
                "? AND state IN ('queued','running','interrupted')",
                (now(), run_id),
            )
        if self.active_id == run_id and self.loop and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)

    def resume(self, run_id: str) -> None:
        """Queue interrupted work, retaining committed results."""
        with catalog_connection(self.store.root) as db:
            changed = db.execute(
                "UPDATE inference_runs SET state = 'queued', error = NULL, "
                "updated_at = ? WHERE id = ? AND state = 'interrupted'",
                (now(), run_id),
            )
            if not changed.rowcount:
                raise ValueError("only interrupted runs can be resumed")

    async def _execute(self, run_id: str) -> None:
        with catalog_connection(self.store.root) as db:
            if not db.execute(
                "UPDATE inference_runs SET state = 'running', updated_at = "
                "? WHERE id = ? AND state = 'queued'",
                (now(), run_id),
            ).rowcount:
                return
            datasets = db.execute(
                "SELECT * FROM inference_run_datasets WHERE run_id = ? ORDER BY dataset_id",
                (run_id,),
            ).fetchall()
            done = {
                (r[0], r[1])
                for r in db.execute(
                    "SELECT dataset_id, ordinal FROM inference_results WHERE run_id = ?", (run_id,)
                )
            }
        frozen = dict(self.store.run(run_id).spec)
        profile = ConnectionProfile.model_validate(frozen.pop("profile"))
        spec = RunSpec.model_validate(frozen)
        generation = spec.generation
        key = os.environ.get(profile.api_key_env, "") if profile.api_key_env else ""
        if profile.api_key_env and not key:
            with catalog_connection(self.store.root) as db:
                db.execute(
                    "UPDATE inference_runs SET state = 'interrupted', error "
                    "= 'configured API key environment variable is missing', updated_at = "
                    "? WHERE id = ?",
                    (now(), run_id),
                )
            return
        semaphore = asyncio.Semaphore(spec.concurrency)
        limiter = RateLimiter(spec.rpm)
        tasks = []
        try:
            async with AsyncOpenAI(
                base_url=profile.base_url, api_key=key or "unused", max_retries=0
            ) as client:
                for dataset in datasets:
                    output = OutputFormat.model_validate_json(dataset["output_format"])
                    for offset in range(0, dataset["rows_kept"], 100):
                        for ordinal, source_index, example in self.store.catalog.inference_rows(
                            dataset["dataset_id"],
                            offset=offset,
                            limit=min(100, dataset["rows_kept"] - offset),
                        ):
                            if (dataset["dataset_id"], ordinal) in done:
                                continue
                            body = compile_request(profile, generation, output, example)
                            tasks.append(
                                asyncio.create_task(
                                    self._row(
                                        client,
                                        run_id,
                                        dataset["dataset_id"],
                                        ordinal,
                                        source_index,
                                        body,
                                        output,
                                        spec,
                                        semaphore,
                                        limiter,
                                        profile.api_key_env is None,
                                    )
                                )
                            )
                            if len(tasks) >= spec.concurrency:
                                finished, pending = await asyncio.wait(
                                    tasks, return_when=asyncio.FIRST_COMPLETED
                                )
                                tasks = list(pending)
                                for task in finished:
                                    task.result()
                await asyncio.gather(*tasks)
            with catalog_connection(self.store.root) as db:
                db.execute(
                    "UPDATE inference_runs SET state = 'completed', "
                    "updated_at = ? WHERE id = ? AND state = 'running'",
                    (now(), run_id),
                )
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            with catalog_connection(self.store.root) as db:
                db.execute(
                    "UPDATE inference_runs SET state = CASE WHEN state = "
                    "'canceling' THEN 'canceled' ELSE 'interrupted' END, updated_at = ? "
                    "WHERE id = ? AND state IN ('running', 'canceling')",
                    (now(), run_id),
                )
            raise
        except Exception as exc:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            error = (
                "endpoint authentication failed"
                if isinstance(exc, AuthenticationFailure)
                else "inference execution failed"
            )
            with catalog_connection(self.store.root) as db:
                db.execute(
                    "UPDATE inference_runs SET state = CASE WHEN state = "
                    "'canceling' THEN 'canceled' ELSE 'interrupted' END, error = ?, "
                    "updated_at = ? WHERE id = ? AND state IN ('running', 'canceling')",
                    (error, now(), run_id),
                )

    async def _row(  # noqa: PLR0913
        self,
        client: AsyncOpenAI,
        run_id: str,
        dataset_id: str,
        ordinal: int,
        source_index: int,
        body: dict[str, Any],
        output: OutputFormat,
        spec: RunSpec,
        semaphore: asyncio.Semaphore,
        limiter: RateLimiter,
        omit_auth: bool,
    ) -> None:
        async with semaphore:
            result = RowResult(
                dataset_id=dataset_id, ordinal=ordinal, source_index=source_index, status="error"
            )
            await send(
                client,
                body,
                output,
                result,
                timeout=spec.timeout_seconds,
                retries=spec.retries,
                limiter=limiter,
                omit_auth=omit_auth,
            )
            with catalog_connection(self.store.root) as db:
                db.execute(
                    "INSERT OR IGNORE INTO inference_results VALUES (?, ?, ?, ?)",
                    (run_id, dataset_id, ordinal, result.model_dump_json()),
                )


class RateLimiter:
    """Sliding-window attempt limiter shared by all rows."""

    def __init__(self, rpm: int) -> None:
        """Configure the rolling request limit."""
        self.rpm = rpm
        self.times: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Count an attempt before sending it."""
        async with self.lock:
            while True:
                now_time = time.monotonic()
                while self.times and self.times[0] <= now_time - 60:
                    self.times.popleft()
                if len(self.times) < self.rpm:
                    self.times.append(now_time)
                    return
                await asyncio.sleep(max(0, self.times[0] + 60 - now_time))
