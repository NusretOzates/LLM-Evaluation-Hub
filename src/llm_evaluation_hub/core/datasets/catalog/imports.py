"""Durable preview, job and provenance persistence without runtime dependencies."""

import fcntl
import json
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from llm_evaluation_hub.core.datasets.catalog.schema import initialize_catalog
from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection
from llm_evaluation_hub.core.datasets.records import dump_json, parse_json_value

_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "interrupted"})
_TRANSITIONS = {
    "queued": {"running", "cancelled", "failed"},
    "running": {"cancelling", "failed", "cancelled", "interrupted"},
    "cancelling": {"cancelled", "failed", "interrupted"},
}
_MUTABLE = frozenset({"state", "phase", "rows_loaded", "rows_kept", "rows_dropped", "error"})


class IdempotencyConflictError(ValueError):
    """A submission reused an idempotency key with different immutable inputs."""


class ImportStateError(ValueError):
    """The requested transition conflicts with the authoritative job state."""


def complete_import(
    connection: sqlite3.Connection,
    import_id: str,
    dataset_id: str,
    counts: tuple[int, int, int],
) -> None:
    """Complete an eligible job inside its dataset publication transaction."""
    loaded, kept, dropped = counts
    cursor = connection.execute(
        "UPDATE import_jobs SET state = 'succeeded', phase = 'completed', dataset_id = ?, "
        "rows_loaded = ?, rows_kept = ?, rows_dropped = ?, updated_at = ?, error = NULL "
        "WHERE id = ? AND state = 'running' AND candidate_dataset_id = ?",
        (dataset_id, loaded, kept, dropped, _now(), import_id, dataset_id),
    )
    if cursor.rowcount != 1:
        raise ImportStateError("import is not running or its candidate dataset differs")


class ImportStore:
    """Persist import specifications and progress in the shared catalog database."""

    def __init__(self, root: Path) -> None:
        """Use the catalog migration owner to initialize shared tables."""
        initialize_catalog(root)
        self._root = root

    @contextmanager
    def decision_lock(self) -> Generator[None, None, None]:
        """Serialize cancellation against the supervisor's final publication decision.

        Hold this lock only after child work stops, never during network/process waits.
        The supervisor holds it while checking state and publishing a completed result.
        """
        with (self._root / ".import-decision.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def put_preview(self, id: str, spec: dict[str, object], expires_at: str | datetime) -> None:
        """Persist a successful immutable attestation, without sample row contents."""
        parse_json_value(spec)
        expiry = expires_at.isoformat() if isinstance(expires_at, datetime) else expires_at
        if datetime.fromisoformat(expiry).tzinfo is None:
            raise ValueError("preview expiry must have a timezone")
        with catalog_connection(self._root) as connection:
            connection.execute(
                "INSERT INTO import_previews(id, spec, expires_at) VALUES (?, ?, ?)",
                (id, dump_json(spec), expiry),
            )

    def get_preview(self, id: str) -> dict[str, object] | None:
        """Return an attestation, including its expiry for domain-level rejection."""
        with catalog_connection(self._root) as connection:
            row = connection.execute("SELECT * FROM import_previews WHERE id = ?", (id,)).fetchone()
            if row is None:
                return None
            return {
                "id": row["id"],
                "spec": json.loads(row["spec"]),
                "expires_at": row["expires_at"],
            }

    def create_job(
        self, name: str, spec: dict[str, object], idempotency_key: str
    ) -> dict[str, object]:
        """Create a queued job, or replay its exact immutable submission."""
        if not name or not idempotency_key:
            raise ValueError("name and idempotency key must not be empty")
        parse_json_value(spec)
        with catalog_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT * FROM import_jobs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if prior is not None:
                if prior["name"] != name or json.loads(prior["spec"]) != spec:
                    raise IdempotencyConflictError("idempotency key belongs to another submission")
                return _job(prior)
            job_id = str(uuid.uuid4())
            created = _now()
            connection.execute(
                "INSERT INTO import_jobs(id, name, state, phase, created_at, updated_at, spec, "
                "candidate_dataset_id, idempotency_key) "
                "VALUES (?, ?, 'queued', 'queued', ?, ?, ?, ?, ?)",
                (
                    job_id,
                    name,
                    created,
                    created,
                    dump_json(spec),
                    str(uuid.uuid4()),
                    idempotency_key,
                ),
            )
            return _require_job(connection, job_id)

    def get_job(self, id: str) -> dict[str, object]:
        """Read one job; unknown identities raise KeyError."""
        with catalog_connection(self._root) as connection:
            return _require_job(connection, id)

    def list_jobs(self) -> list[dict[str, object]]:
        """Return persisted jobs newest first."""
        with catalog_connection(self._root) as connection:
            return [
                _job(row)
                for row in connection.execute(
                    "SELECT * FROM import_jobs ORDER BY created_at DESC, id DESC"
                )
            ]

    def update_job(self, id: str, **fields: object) -> dict[str, object]:
        """Update mutable progress/state; publication alone can mark success."""
        if not fields or fields.keys() - _MUTABLE:
            raise ValueError("unsupported or empty job update")
        for key in ("rows_loaded", "rows_kept", "rows_dropped"):
            value = fields.get(key, 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("job counts must be nonnegative integers")
        if "error" in fields:
            parse_json_value(fields["error"])
        with catalog_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = _require_job(connection, id)
            state = job["state"]
            target = fields.get("state", state)
            if state in _TERMINAL:
                return job
            if target != state and target not in _TRANSITIONS.get(state, set()):
                raise ImportStateError("invalid import state transition")
            stored = dict(fields)
            if "error" in stored and stored["error"] is not None:
                stored["error"] = dump_json(stored["error"])
            stored["updated_at"] = _now()
            assignments = ", ".join(f"{key} = ?" for key in stored)
            connection.execute(
                f"UPDATE import_jobs SET {assignments} WHERE id = ?", (*stored.values(), id)
            )
            return _require_job(connection, id)

    def request_cancel(self, id: str) -> dict[str, object]:
        """Cancel queued work or request cancellation, respecting committed success."""
        with self.decision_lock():
            job = self.get_job(id)
            if job["state"] in _TERMINAL or job["state"] == "cancelling":
                return job
            target = "cancelled" if job["state"] == "queued" else "cancelling"
            return self.update_job(id, state=target, phase=target)

    def recover_interrupted(self) -> list[dict[str, object]]:
        """Reconcile committed datasets and interrupt active attempts; preserve queued jobs."""
        with self.decision_lock(), catalog_connection(self._root) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM import_jobs WHERE state IN ('running', 'cancelling')"
            ).fetchall()
            for row in rows:
                dataset = connection.execute(
                    "SELECT id FROM datasets WHERE id = ?", (row["candidate_dataset_id"],)
                ).fetchone()
                connection.execute(
                    "UPDATE import_jobs SET state = ?, phase = ?, dataset_id = ?, updated_at = ? "
                    "WHERE id = ?",
                    (
                        "succeeded" if dataset else "interrupted",
                        "completed" if dataset else "interrupted",
                        dataset["id"] if dataset else None,
                        _now(),
                        row["id"],
                    ),
                )
            return [_require_job(connection, row["id"]) for row in rows]


def _now() -> str:
    """Return a timezone-aware durable timestamp."""
    return datetime.now(UTC).isoformat()


def _job(row: sqlite3.Row) -> dict[str, object]:
    """Decode JSON fields while retaining internal scheduling identities."""
    job = dict(row)
    job["spec"] = json.loads(row["spec"])
    job["error"] = None if row["error"] is None else json.loads(row["error"])
    return job


def _require_job(connection: sqlite3.Connection, id: str) -> dict[str, object]:
    """Read an authoritative job inside the caller's transaction."""
    row = connection.execute("SELECT * FROM import_jobs WHERE id = ?", (id,)).fetchone()
    if row is None:
        raise KeyError(id)
    return _job(row)
