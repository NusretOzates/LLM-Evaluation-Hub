"""Durable evaluation manifests and outcomes in the catalog."""

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from llm_evaluation_hub.core.datasets.catalog import DatasetRepository
from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection
from llm_evaluation_hub.evaluation.contracts import Definition, MethodContext
from llm_evaluation_hub.evaluation.registry import METHODS, MethodDefinition
from llm_evaluation_hub.inference.store import encode, now


class EvaluationStore:
    """Own definitions and frozen evaluation state."""

    def __init__(self, root: Path) -> None:
        """Initialize the owned evaluation state."""
        self.root = root
        self.catalog = DatasetRepository(root)

    def definitions(self) -> list[dict[str, Any]]:
        """Definitions."""
        with catalog_connection(self.root) as db:
            return [
                {"id": row["id"], **json.loads(row["settings"])}
                for row in db.execute("SELECT * FROM evaluation_definitions ORDER BY name")
            ]

    def save_definition(
        self, definition: Definition, identifier: str | None = None
    ) -> dict[str, Any]:
        """Save definition."""
        method = METHODS.get(definition.method_id)
        if method is None:
            raise ValueError("unknown evaluation method")
        method.config_model.model_validate(definition.method_config)
        identifier = identifier or str(uuid.uuid4())
        timestamp = now()
        with catalog_connection(self.root) as db:
            db.execute(
                (
                    "INSERT INTO evaluation_definitions VALUES (?, ?, ?, ?, ?) ON "
                    "CONFLICT(id) DO UPDATE SET name=excluded.name, "
                    "settings=excluded.settings, updated_at=excluded.updated_at"
                ),
                (identifier, definition.name, definition.model_dump_json(), timestamp, timestamp),
            )
        return {"id": identifier, **definition.model_dump(mode="json")}

    def create(
        self, source_id: str, dataset_ids: list[str], definition: Definition
    ) -> dict[str, Any]:
        """Freeze source availability, row identities, tags and method settings atomically."""
        if not dataset_ids:
            raise ValueError("select at least one dataset")
        method = METHODS.get(definition.method_id)
        if method is None:
            raise ValueError("unknown evaluation method")
        config = method.resolve_config(definition.method_config, self)
        schema = method.result_schema(config)
        Draft202012Validator.check_schema(schema)
        if schema.get("type") != "object":
            raise ValueError("method result schema must have an object root")
        frozen = definition.model_dump(mode="json")
        frozen.update(
            method_config=config,
            method_version=method.version,
            result_schema=schema,
        )
        run_id = str(uuid.uuid4())
        timestamp = now()
        with catalog_connection(self.root) as db:
            db.execute("BEGIN IMMEDIATE")
            source = db.execute(
                "SELECT state FROM inference_runs WHERE id = ?", (source_id,)
            ).fetchone()
            if source is None:
                raise KeyError("source run not found")
            if source[0] not in ("completed", "canceled", "interrupted"):
                raise ValueError("source inference run must be terminal")
            selected = self._selected(db, source_id, dataset_ids)
            total = sum(row["rows_kept"] for row, _ in selected)
            db.execute(
                "INSERT INTO evaluation_runs VALUES (?, ?, 'queued', ?, ?, ?, ?, NULL)",
                (run_id, source_id, encode(frozen), total, timestamp, timestamp),
            )
            for dataset, tags in selected:
                dataset_id = dataset["dataset_id"]
                db.execute(
                    "INSERT INTO evaluation_run_datasets VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        dataset_id,
                        dataset["name"],
                        dataset["snapshot_path"],
                        dataset["snapshot_format_version"],
                        dataset["rows_kept"],
                        encode(tags),
                    ),
                )
                for offset in range(0, dataset["rows_kept"], 100):
                    rows = self.catalog.evaluation_rows(dataset_id, offset=offset, limit=100)
                    if len(rows) != min(100, dataset["rows_kept"] - offset):
                        raise ValueError(f"{dataset['name']}: source snapshot is incomplete")
                    for ordinal, source_index, example in rows:
                        result = db.execute(
                            (
                                "SELECT payload FROM inference_results WHERE run_id=? AND "
                                "dataset_id=? AND ordinal=?"
                            ),
                            (source_id, dataset_id, ordinal),
                        ).fetchone()
                        payload = json.loads(result[0]) if result else None
                        if payload and payload["source_index"] != source_index:
                            raise ValueError(
                                f"{dataset['name']} row {ordinal}: source index mismatch"
                            )
                        db.execute(
                            "INSERT INTO evaluation_inputs VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                run_id,
                                dataset_id,
                                ordinal,
                                source_index,
                                int(payload is not None),
                                payload["status"] if payload else None,
                                encode(example.segments),
                            ),
                        )
            self._preflight(db, source_id, selected, method, config)
        return self.run(run_id)

    def _selected(
        self, db: sqlite3.Connection, source_id: str, dataset_ids: list[str]
    ) -> list[tuple[sqlite3.Row, list[str]]]:
        """Resolve selected snapshots and their current tag attribution."""
        selected = []
        for dataset_id in sorted(set(dataset_ids)):
            row = db.execute(
                (
                    "SELECT d.* FROM inference_run_datasets d JOIN datasets s ON "
                    "s.id=d.dataset_id WHERE d.run_id=? AND d.dataset_id=? AND "
                    "s.purge_pending=0"
                ),
                (source_id, dataset_id),
            ).fetchone()
            if row is None:
                raise ValueError("selected source dataset is unavailable")
            live = db.execute(
                "SELECT parquet_path, snapshot_format_version FROM datasets WHERE id=?",
                (dataset_id,),
            ).fetchone()
            if (
                live["parquet_path"] != row["snapshot_path"]
                or live["snapshot_format_version"] != row["snapshot_format_version"]
            ):
                raise ValueError("selected source snapshot no longer matches its manifest")
            tags = [
                tag[0]
                for tag in db.execute(
                    (
                        "SELECT t.path FROM tags t JOIN dataset_tags dt ON dt.tag_id=t.id "
                        "WHERE dt.dataset_id=? ORDER BY t.path"
                    ),
                    (dataset_id,),
                )
            ]
            selected.append((row, tags))
        return selected

    def _preflight(
        self,
        db: sqlite3.Connection,
        source_id: str,
        selected: list[tuple[sqlite3.Row, list[str]]],
        method: MethodDefinition,
        config: dict[str, Any],
    ) -> None:
        """Validate required prompt inputs before committing the manifest."""
        if method.preflight is not None:
            allowed = {
                "conversation",
                "response.content",
                "response.parsed",
                "response.tool_calls",
                "processed_response",
                "expected_output",
            }
            for dataset, _ in selected:
                for offset in range(0, dataset["rows_kept"], 100):
                    for _, _, example in self.catalog.evaluation_rows(
                        dataset["dataset_id"], offset=offset, limit=100
                    ):
                        allowed.update(f"extras.{key}" for key in example.extras)
                        allowed.update(f"segments.{key}" for key in example.segments)
            if method.validate_fields is not None:
                method.validate_fields(config, allowed)
            for dataset, _ in selected:
                for offset in range(0, dataset["rows_kept"], 100):
                    for ordinal, source_index, example in self.catalog.evaluation_rows(
                        dataset["dataset_id"], offset=offset, limit=100
                    ):
                        saved = db.execute(
                            (
                                "SELECT payload FROM inference_results WHERE run_id=? AND "
                                "dataset_id=? AND ordinal=?"
                            ),
                            (source_id, dataset["dataset_id"], ordinal),
                        ).fetchone()
                        response = json.loads(saved[0]) if saved else None
                        if response and response["status"] == "ok":
                            context = MethodContext(
                                example,
                                response,
                                "candidate",
                                dataset["dataset_id"],
                                ordinal,
                                source_index,
                            )
                            try:
                                method.preflight(config, context, allowed)
                            except ValueError as exc:
                                raise ValueError(f"{dataset['name']} row {ordinal}: {exc}") from exc

    def run(self, run_id: str) -> dict[str, Any]:
        """Run."""
        with catalog_connection(self.root) as db:
            row = db.execute(
                (
                    "SELECT *, (SELECT count(*) FROM evaluation_results WHERE "
                    "run_id=evaluation_runs.id) AS completed FROM evaluation_runs "
                    "WHERE id=?"
                ),
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError("evaluation not found")
            result = dict(row)
            result["settings"] = json.loads(result["settings"])
            result["datasets"] = [
                {**dict(d), "tags": json.loads(d["tags"])}
                for d in db.execute(
                    "SELECT * FROM evaluation_run_datasets WHERE run_id=? ORDER BY name", (run_id,)
                )
            ]
            return result

    def runs(self) -> list[dict[str, Any]]:
        """Runs."""
        with catalog_connection(self.root) as db:
            identifiers = [
                r[0] for r in db.execute("SELECT id FROM evaluation_runs ORDER BY created_at DESC")
            ]
        return [self.run(identifier) for identifier in identifiers]

    def delete(self, run_id: str) -> None:
        """Delete."""
        with catalog_connection(self.root) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM evaluation_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError("evaluation not found")
            if row[0] in ("queued", "running", "canceling"):
                raise ValueError("cancel the evaluation before deleting it")
            for table in ("evaluation_results", "evaluation_inputs", "evaluation_run_datasets"):
                db.execute(f"DELETE FROM {table} WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM evaluation_runs WHERE id=?", (run_id,))
