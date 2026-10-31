"""SQLite persistence for inference profiles, configuration and results."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from llm_evaluation_hub.core.datasets.catalog import DatasetRepository
from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection
from llm_evaluation_hub.inference.compiler import compile_request, validate_format
from llm_evaluation_hub.inference.contracts import (
    ConnectionProfile,
    FrozenDataset,
    OutputFormat,
    ResultPage,
    RowResult,
    RunSpec,
    RunView,
)


def now() -> str:
    """Return a UTC timestamp."""
    return datetime.now(UTC).isoformat()


def encode(value: object) -> str:
    """Encode JSON for SQLite."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class InferenceStore:
    """Own inference metadata in the catalog database."""

    def __init__(self, root: Path) -> None:
        """Bind persistence to a catalog directory."""
        self.root = root
        self.catalog = DatasetRepository(root)

    def profiles(self) -> list[ConnectionProfile]:
        """List saved profiles."""
        with catalog_connection(self.root) as db:
            return [
                ConnectionProfile.model_validate_json(row[0])
                for row in db.execute("SELECT payload FROM inference_profiles ORDER BY id")
            ]

    def profile(self, profile_id: str) -> ConnectionProfile:
        """Read a profile by ID."""
        with catalog_connection(self.root) as db:
            row = db.execute(
                "SELECT payload FROM inference_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        if row is None:
            raise KeyError("profile not found")
        return ConnectionProfile.model_validate_json(row[0])

    def save_profile(self, profile: ConnectionProfile) -> ConnectionProfile:
        """Insert or replace a credential-free profile."""
        profile = profile.model_copy(update={"id": profile.id or str(uuid.uuid4())})
        with catalog_connection(self.root) as db:
            db.execute(
                "INSERT OR REPLACE INTO inference_profiles VALUES (?, ?)",
                (profile.id, profile.model_dump_json()),
            )
        return profile

    def delete_profile(self, profile_id: str) -> None:
        """Delete a profile without affecting frozen runs."""
        with catalog_connection(self.root) as db:
            db.execute("DELETE FROM inference_profiles WHERE id = ?", (profile_id,))

    def output(self, dataset_id: str) -> OutputFormat:
        """Return mutable output metadata, defaulting old datasets to text."""
        self.catalog.get_by_id(dataset_id)
        with catalog_connection(self.root) as db:
            row = db.execute(
                "SELECT payload FROM dataset_output_formats WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()
        return OutputFormat() if row is None else OutputFormat.model_validate_json(row[0])

    def save_output(self, dataset_id: str, output: OutputFormat) -> OutputFormat:
        """Update metadata without changing the snapshot."""
        validate_format(output)
        self.catalog.get_by_id(dataset_id)
        with catalog_connection(self.root) as db:
            db.execute(
                "INSERT OR REPLACE INTO dataset_output_formats VALUES (?, ?)",
                (dataset_id, output.model_dump_json(by_alias=True)),
            )
        return output

    def create(self, spec: RunSpec) -> RunView:
        """Freeze profile, dataset identities and output settings atomically."""
        profile = self.profile(spec.profile_id)
        dataset_ids = set(spec.dataset_ids)
        for tag in spec.tags:
            dataset_ids.update(record.id for record in self.catalog.list_datasets(tag=tag))
        if not dataset_ids:
            raise ValueError("select at least one dataset")
        run_id = str(uuid.uuid4())
        timestamp = now()
        with catalog_connection(self.root) as db:
            db.execute("BEGIN IMMEDIATE")
            datasets = []
            for dataset_id in sorted(dataset_ids):
                row = db.execute(
                    "SELECT * FROM datasets WHERE id = ? AND trashed_at IS "
                    "NULL AND purge_pending = 0",
                    (dataset_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("selected dataset is unavailable")
                saved = db.execute(
                    "SELECT payload FROM dataset_output_formats WHERE dataset_id = ?", (dataset_id,)
                ).fetchone()
                output = spec.output_overrides.get(dataset_id) or (
                    OutputFormat() if saved is None else OutputFormat.model_validate_json(saved[0])
                )
                validate_format(output)
                count = row["rows_kept"]
                for offset in range(0, count, 100):
                    for _, source_index, example in self.catalog.inference_rows(
                        dataset_id, offset=offset, limit=min(100, count - offset)
                    ):
                        try:
                            compile_request(profile, spec.generation, output, example)
                        except ValueError as exc:
                            raise ValueError(
                                f"{row['name']} source row {source_index}: {exc}"
                            ) from exc
                datasets.append((row, output, count))
            frozen = spec.model_dump(mode="json", by_alias=True)
            frozen["profile"] = profile.model_dump(mode="json")
            total = sum(count for _, _, count in datasets)
            db.execute(
                "INSERT INTO inference_runs (id, state, created_at, "
                "updated_at, spec, total) VALUES (?, 'queued', ?, ?, ?, ?)",
                (run_id, timestamp, timestamp, encode(frozen), total),
            )
            for row, output, count in datasets:
                db.execute(
                    "INSERT INTO inference_run_datasets (run_id, "
                    "dataset_id, name, snapshot_path, rows_kept, output_format, "
                    "snapshot_format_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        row["id"],
                        row["name"],
                        row["parquet_path"],
                        count,
                        output.model_dump_json(by_alias=True),
                        row["snapshot_format_version"],
                    ),
                )
        return self.run(run_id)

    def run(self, run_id: str) -> RunView:
        """Return a run and committed result count."""
        with catalog_connection(self.root) as db:
            row = db.execute(
                "SELECT *, (SELECT count(*) FROM inference_results WHERE "
                "run_id = inference_runs.id) AS completed FROM inference_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            datasets = db.execute(
                "SELECT d.*, EXISTS(SELECT 1 FROM datasets WHERE id = "
                "d.dataset_id AND purge_pending = 0) AS input_available, "
                "(SELECT count(*) FROM inference_results r WHERE r.run_id = "
                "d.run_id AND r.dataset_id = d.dataset_id) AS completed, "
                "(SELECT count(*) FROM inference_results r WHERE r.run_id = "
                "d.run_id AND r.dataset_id = d.dataset_id AND json_extract(r.payload, "
                "'$.status') != 'ok') AS errors "
                "FROM inference_run_datasets d WHERE d.run_id = ? ORDER BY d.name",
                (run_id,),
            ).fetchall()
        if row is None:
            raise KeyError("run not found")
        return RunView(
            id=row["id"],
            state=row["state"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            spec=json.loads(row["spec"]),
            completed=row["completed"],
            total=row["total"],
            datasets=[
                FrozenDataset(
                    id=d["dataset_id"],
                    name=d["name"],
                    snapshot_format_version=d["snapshot_format_version"],
                    rows=d["rows_kept"],
                    output=OutputFormat.model_validate_json(d["output_format"]),
                    completed=d["completed"],
                    errors=d["errors"],
                    input_available=bool(d["input_available"]),
                )
                for d in datasets
            ],
        )

    def runs(self) -> list[RunView]:
        """List runs newest first."""
        with catalog_connection(self.root) as db:
            ids = [
                row[0]
                for row in db.execute("SELECT id FROM inference_runs ORDER BY created_at DESC")
            ]
        return [self.run(run_id) for run_id in ids]

    def results(
        self,
        run_id: str,
        offset: int,
        limit: int,
        *,
        dataset_id: str | None = None,
        errors_only: bool = False,
    ) -> ResultPage:
        """Read a page after filtering across the entire run."""
        self.run(run_id)
        clauses = ["run_id = ?"]
        params: list[object] = [run_id]
        if dataset_id is not None:
            clauses.append("dataset_id = ?")
            params.append(dataset_id)
        if errors_only:
            clauses.append("json_extract(payload, '$.status') != 'ok'")
        where = " AND ".join(clauses)
        with catalog_connection(self.root) as db:
            total = db.execute(
                f"SELECT count(*) FROM inference_results WHERE {where}", params
            ).fetchone()[0]
            rows = db.execute(
                f"SELECT payload FROM inference_results WHERE {where} "
                "ORDER BY dataset_id, ordinal LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return ResultPage(
            results=[RowResult.model_validate_json(row[0]) for row in rows],
            total=total,
            offset=offset,
            limit=limit,
        )
