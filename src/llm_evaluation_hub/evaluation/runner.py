"""Background evaluation execution with incremental results and recovery."""

import asyncio
import contextlib
import fcntl
import json
import sqlite3
import threading
from typing import Any

from jsonschema import Draft202012Validator

from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection
from llm_evaluation_hub.evaluation.contracts import (
    Definition,
    EvaluationSession,
    MethodContext,
    MethodFailure,
    SourceIneligible,
)
from llm_evaluation_hub.evaluation.registry import METHODS
from llm_evaluation_hub.evaluation.scoring import preprocess, score
from llm_evaluation_hub.evaluation.store import EvaluationStore
from llm_evaluation_hub.inference.store import encode, now
from llm_evaluation_hub.inference.transport import AuthenticationFailure


class EvaluationRunner:
    """One catalog-owned runner with explicit recovery."""

    def __init__(self, store: EvaluationStore, admission: threading.Lock) -> None:
        """Initialize the owned evaluation state."""
        self.store, self.admission = store, admission
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.task: asyncio.Task[None] | None = None
        self.active_id: str | None = None
        self.lock_file: Any = None
        self.ready = threading.Event()
        self.stopping = False

    def start(self) -> None:
        """Start."""
        self.lock_file = (self.store.root / ".evaluation.lock").open("a")
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            self.lock_file = None
            raise RuntimeError("another evaluation runner owns this catalog") from None
        with catalog_connection(self.store.root) as db:
            db.execute(
                (
                    "UPDATE evaluation_runs SET state=CASE WHEN state='canceling' THEN"
                    " 'canceled' ELSE 'interrupted' END, updated_at=? WHERE state IN "
                    "('queued','running','canceling')"
                ),
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
                    "SELECT id FROM evaluation_runs WHERE state='queued' ORDER BY "
                    "created_at LIMIT 1"
                ).fetchone()
            if row is None:
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
                        (
                            "UPDATE evaluation_runs SET state='interrupted', error='evaluation"
                            " execution failed', updated_at=? WHERE id=? AND state='running'"
                        ),
                        (now(), row[0]),
                    )
            finally:
                with catalog_connection(self.store.root) as db:
                    db.execute(
                        (
                            "UPDATE evaluation_runs SET state='canceled', updated_at=? WHERE "
                            "id=? AND state='canceling'"
                        ),
                        (now(), row[0]),
                    )
                self.task = None
                self.active_id = None

    def stop(self) -> None:
        """Stop."""
        if self.loop:
            self.loop.call_soon_threadsafe(self._shutdown)
        if self.thread:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise RuntimeError("evaluation runner did not stop")
        if self.lock_file:
            self.lock_file.close()
            self.lock_file = None

    def _shutdown(self) -> None:
        self.stopping = True
        for task in asyncio.all_tasks():
            task.cancel()

    def cancel(self, run_id: str) -> None:
        """Cancel."""
        self.store.run(run_id)
        with catalog_connection(self.store.root) as db:
            db.execute(
                (
                    "UPDATE evaluation_runs SET state=CASE WHEN state='running' THEN "
                    "'canceling' ELSE 'canceled' END, updated_at=? WHERE id=? AND "
                    "state IN ('queued','running','interrupted')"
                ),
                (now(), run_id),
            )
        if self.active_id == run_id and self.loop and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)

    def resume(self, run_id: str) -> None:
        """Resume."""
        run = self.store.run(run_id)
        method = METHODS.get(run["settings"]["method_id"])
        if method is None or method.version != run["settings"]["method_version"]:
            raise ValueError("evaluation method version is unavailable")
        with catalog_connection(self.store.root) as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute(
                    "SELECT 1 FROM inference_runs WHERE id=?", (run["source_inference_run_id"],)
                ).fetchone()
                is None
            ):
                raise ValueError("source inference run is unavailable")
            datasets = db.execute(
                "SELECT dataset_id FROM evaluation_run_datasets WHERE run_id=?", (run_id,)
            ).fetchall()
            for dataset in datasets:
                self.store.catalog.evaluation_rows(dataset[0], offset=0, limit=1)
            if not db.execute(
                (
                    "UPDATE evaluation_runs SET state='queued', error=NULL, "
                    "updated_at=? WHERE id=? AND state='interrupted'"
                ),
                (now(), run_id),
            ).rowcount:
                raise ValueError("only interrupted evaluations can resume")

    async def _execute(self, run_id: str) -> None:
        run = self.store.run(run_id)
        settings = dict(run["settings"])
        method = METHODS[settings["method_id"]]
        definition = Definition.model_validate(
            {key: settings[key] for key in Definition.model_fields}
        )
        admitted = False
        try:
            if method.resource == "model_endpoint":
                while not self.admission.acquire(blocking=False):
                    await asyncio.sleep(0.1)
                    if self.store.run(run_id)["state"] != "queued":
                        return
                admitted = True
            with catalog_connection(self.store.root) as db:
                if not db.execute(
                    (
                        "UPDATE evaluation_runs SET state='running', updated_at=? WHERE "
                        "id=? AND state='queued'"
                    ),
                    (now(), run_id),
                ).rowcount:
                    return
            async with method.open(settings["method_config"], self.store) as session:
                while True:
                    with catalog_connection(self.store.root) as db:
                        rows = db.execute(
                            (
                                "SELECT i.* FROM evaluation_inputs i LEFT JOIN evaluation_results "
                                "r USING(run_id,dataset_id,ordinal) WHERE i.run_id=? AND r.run_id "
                                "IS NULL ORDER BY i.dataset_id,i.ordinal LIMIT ?"
                            ),
                            (run_id, definition.concurrency),
                        ).fetchall()
                    if not rows:
                        break
                    tasks = [
                        asyncio.create_task(
                            self._evaluate_row(run, definition, settings, row, session)
                        )
                        for row in rows
                    ]
                    try:
                        await asyncio.gather(*tasks)
                    finally:
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
            with catalog_connection(self.store.root) as db:
                db.execute(
                    (
                        "UPDATE evaluation_runs SET state='completed', updated_at=? WHERE "
                        "id=? AND state='running'"
                    ),
                    (now(), run_id),
                )
        finally:
            if admitted:
                self.admission.release()

    async def _evaluate_row(
        self,
        run: dict[str, Any],
        definition: Definition,
        settings: dict[str, Any],
        row: sqlite3.Row,
        session: EvaluationSession,
    ) -> None:
        status, stage, judgment, scores, evidence, error, elapsed, attempts, usage = (
            "failed",
            "source",
            None,
            None,
            None,
            None,
            None,
            0,
            None,
        )
        if not row["source_result_present"] or row["source_status"] != "ok":
            status, error = "source_ineligible", "source prediction is unavailable or unsuccessful"
        else:
            try:
                example_row = self.store.catalog.evaluation_rows(
                    row["dataset_id"], offset=row["ordinal"], limit=1
                )[0]
                if example_row[1] != row["source_index"]:
                    raise ValueError("source index mismatch")
                with catalog_connection(self.store.root) as db:
                    source = db.execute(
                        (
                            "SELECT payload FROM inference_results WHERE run_id=? AND "
                            "dataset_id=? AND ordinal=?"
                        ),
                        (run["source_inference_run_id"], row["dataset_id"], row["ordinal"]),
                    ).fetchone()
                response = json.loads(source[0])
                method = METHODS[definition.method_id]
                if method.check_source is not None:
                    method.check_source(example_row[2])
                stage = "preprocess"
                candidate = preprocess(response, definition.preprocess_source)
                stage = "method"
                outcome = await session.evaluate(
                    MethodContext(
                        example_row[2],
                        response,
                        candidate,
                        row["dataset_id"],
                        row["ordinal"],
                        row["source_index"],
                    )
                )
                judgment, evidence, elapsed, attempts, usage = (
                    outcome.result,
                    outcome.evidence,
                    outcome.elapsed_ms,
                    outcome.attempts,
                    outcome.usage,
                )
                Draft202012Validator(settings["result_schema"]).validate(judgment)
                stage = "score"
                scores = score(judgment, definition.scoring_source, definition.metrics)
                status, stage = "scored", "complete"
            except AuthenticationFailure:
                raise
            except SourceIneligible as exc:
                status, stage, error = "source_ineligible", "source", str(exc)
            except MethodFailure as exc:
                error, evidence, elapsed, attempts, usage = (
                    str(exc),
                    exc.evidence,
                    exc.elapsed_ms,
                    exc.attempts,
                    exc.usage,
                )
            except Exception as exc:
                error = f"{stage} failed ({type(exc).__name__})"
        with catalog_connection(self.store.root) as db:
            db.execute(
                (
                    "INSERT OR IGNORE INTO evaluation_results VALUES (?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    run["id"],
                    row["dataset_id"],
                    row["ordinal"],
                    status,
                    stage,
                    encode(judgment) if judgment is not None else None,
                    encode(scores) if scores is not None else None,
                    encode(evidence) if evidence is not None else None,
                    error,
                    elapsed,
                    attempts,
                    encode(usage) if usage is not None else None,
                ),
            )
