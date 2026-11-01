"""Evaluation definitions, execution and reports."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import BaseModel, Field

from llm_evaluation_hub.api.inference_routes import input_errors
from llm_evaluation_hub.core.datasets.catalog import UnknownDatasetError
from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection
from llm_evaluation_hub.evaluation.contracts import Definition, MethodContext, MethodFailure
from llm_evaluation_hub.evaluation.registry import METHODS
from llm_evaluation_hub.evaluation.scoring import preprocess, score
from llm_evaluation_hub.execution.python import ProcessorError

router = APIRouter()


class CreateEvaluation(BaseModel):
    """Hold CreateEvaluation fields."""

    source_inference_run_id: str
    dataset_ids: list[str] = Field(min_length=1)
    definition: Definition


class ScoringTest(BaseModel):
    """Hold Scoring test fields."""

    result: dict[str, Any]
    scoring_source: str
    result_schema: dict[str, Any]


@router.get("/evaluation-methods")
def methods() -> list[dict[str, Any]]:
    """Methods."""
    return [
        {
            "id": m.id,
            "version": m.version,
            "label": m.label,
            "config_schema": m.config_model.model_json_schema(),
            "default_config": m.config_model.model_json_schema().get("properties", {}),
            "default_scoring": m.default_scoring,
            "resource": m.resource,
        }
        for m in METHODS.values()
    ]


@router.get("/evaluation-definitions")
def definitions(request: Request) -> list[dict[str, Any]]:
    """Definitions."""
    return request.app.state.evaluation_store.definitions()


@router.get("/evaluation-definitions/{identifier}")
@input_errors
def definition(identifier: str, request: Request) -> dict[str, Any]:
    """Read one reusable definition."""
    for item in request.app.state.evaluation_store.definitions():
        if item["id"] == identifier:
            return item
    raise KeyError("definition not found")


@router.post("/evaluation-definitions")
@input_errors
def save_definition(definition: Definition, request: Request) -> dict[str, Any]:
    """Save definition."""
    return request.app.state.evaluation_store.save_definition(definition)


@router.put("/evaluation-definitions/{identifier}")
@input_errors
def update_definition(identifier: str, definition: Definition, request: Request) -> dict[str, Any]:
    """Update definition."""
    return request.app.state.evaluation_store.save_definition(definition, identifier)


@router.delete("/evaluation-definitions/{identifier}", status_code=204)
def delete_definition(identifier: str, request: Request) -> None:
    """Delete definition."""
    with catalog_connection(request.app.state.evaluation_store.root) as db:
        if not db.execute("DELETE FROM evaluation_definitions WHERE id=?", (identifier,)).rowcount:
            raise HTTPException(404, "definition not found")


@router.post("/evaluations/test-scoring")
@input_errors
def test_scoring(data: ScoringTest) -> dict[str, Any]:
    """Test scoring."""
    Draft202012Validator.check_schema(data.result_schema)
    try:
        Draft202012Validator(data.result_schema).validate(data.result)
        return {"scores": score(data.result, data.scoring_source), "synthetic": True}
    except SchemaValidationError:
        raise HTTPException(422, "result does not match the method schema") from None
    except ProcessorError as exc:
        raise HTTPException(422, exc.message) from None


@router.post("/evaluations")
@input_errors
def create_evaluation(data: CreateEvaluation, request: Request) -> dict[str, Any]:
    """Create evaluation."""
    return request.app.state.evaluation_store.create(
        data.source_inference_run_id, data.dataset_ids, data.definition
    )


@router.get("/evaluations")
def evaluations(request: Request) -> list[dict[str, Any]]:
    """Evaluations."""
    return request.app.state.evaluation_store.runs()


@router.get("/evaluations/{run_id}")
@input_errors
def evaluation(run_id: str, request: Request) -> dict[str, Any]:
    """Evaluation."""
    return request.app.state.evaluation_store.run(run_id)


@router.delete("/evaluations/{run_id}", status_code=204)
def delete_evaluation(run_id: str, request: Request) -> None:
    """Delete evaluation."""
    try:
        request.app.state.evaluation_store.delete(run_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/evaluations/{run_id}/cancel")
@input_errors
def cancel(run_id: str, request: Request) -> dict[str, Any]:
    """Cancel."""
    request.app.state.evaluation_runner.cancel(run_id)
    return request.app.state.evaluation_store.run(run_id)


@router.post("/evaluations/{run_id}/resume")
@input_errors
def resume(run_id: str, request: Request) -> dict[str, Any]:
    """Resume."""
    try:
        request.app.state.evaluation_runner.resume(run_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return request.app.state.evaluation_store.run(run_id)


def scope_sql(run_id: str, dataset_ids: list[str], tag_paths: list[str]) -> tuple[str, list[Any]]:
    """Build the same frozen dataset-and-tag population filter for both views."""
    clauses = ["i.run_id=?"]
    params: list[Any] = [run_id]
    if dataset_ids:
        clauses.append("i.dataset_id IN (" + ",".join("?" for _ in dataset_ids) + ")")
        params.extend(dataset_ids)
    if tag_paths:
        clauses.append(
            "EXISTS (SELECT 1 FROM json_each(d.tags) t WHERE "
            + " OR ".join(
                "(t.value=? OR substr(t.value,1,length(?)+1)=? || '/')" for _ in tag_paths
            )
            + ")"
        )
        for path in tag_paths:
            params.extend((path, path, path))
    return " AND ".join(clauses), params


class ResultFilters(BaseModel):
    """Scope and pagination for result rows."""

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)
    dataset_ids: list[str] = Field(default_factory=list)
    tag_paths: list[str] = Field(default_factory=list)
    status: str | None = None


class SummaryFilters(BaseModel):
    """Shared population scope and summary grouping."""

    group_by: str = "overall"
    segment_key: str | None = None
    dataset_ids: list[str] = Field(default_factory=list)
    tag_paths: list[str] = Field(default_factory=list)


@router.get("/evaluations/{run_id}/results")
@input_errors
def results(
    run_id: str, request: Request, filters: Annotated[ResultFilters, Query()]
) -> dict[str, Any]:
    """Results."""
    store = request.app.state.evaluation_store
    store.run(run_id)
    where, params = scope_sql(run_id, filters.dataset_ids, filters.tag_paths)
    if filters.status:
        where += " AND COALESCE(r.status, 'pending') = ?"
        params.append(filters.status)
    join = (
        " FROM evaluation_inputs i JOIN evaluation_run_datasets d "
        "USING(run_id,dataset_id) LEFT JOIN evaluation_results r "
        "USING(run_id,dataset_id,ordinal) WHERE "
    ) + where
    with catalog_connection(store.root) as db:
        total = db.execute("SELECT count(*)" + join, params).fetchone()[0]
        rows = db.execute(
            (
                "SELECT i.*, r.status, r.stage, r.result, r.scores, r.evidence, "
                "r.error, r.elapsed_ms, r.attempts, r.usage"
            )
            + join
            + " ORDER BY i.dataset_id,i.ordinal LIMIT ? OFFSET ?",
            [*params, filters.limit, filters.offset],
        ).fetchall()
    output = []
    for row in rows:
        value = dict(row)
        for key in ("segments", "result", "scores", "evidence", "usage"):
            if value[key] is not None:
                value[key] = json.loads(value[key])
        output.append(value)
    return {"results": output, "total": total, "offset": filters.offset, "limit": filters.limit}


@router.get("/evaluations/{run_id}/summary")
@input_errors
def summary(
    run_id: str, request: Request, filters: Annotated[SummaryFilters, Query()]
) -> dict[str, Any]:
    """Aggregate over the complete manifest, retaining unsuccessful rows in coverage."""
    if filters.group_by not in ("overall", "dataset", "segment", "tag"):
        raise ValueError("unknown grouping")
    store = request.app.state.evaluation_store
    run = store.run(run_id)
    groups: dict[str | None, dict[str, Any]] = {}
    where, params = scope_sql(run_id, filters.dataset_ids, filters.tag_paths)
    with catalog_connection(store.root) as db:
        rows = db.execute(
            (
                "SELECT i.dataset_id, i.segments, d.name, d.tags, r.status, "
                "r.scores FROM evaluation_inputs i JOIN evaluation_run_datasets d "
                "USING(run_id,dataset_id) LEFT JOIN evaluation_results r "
                "USING(run_id,dataset_id,ordinal) WHERE "
            )
            + where,
            params,
        )
        for row in rows:
            if filters.group_by == "dataset":
                keys = [row["name"]]
            elif filters.group_by == "segment":
                keys = [json.loads(row["segments"]).get(filters.segment_key)]
            elif filters.group_by == "tag":
                tags = json.loads(row["tags"])
                keys = sorted(
                    {
                        "/".join(tag.split("/")[:n])
                        for tag in tags
                        for n in range(1, len(tag.split("/")) + 1)
                    }
                ) or [None]
            else:
                keys = ["Overall"]
            for key in keys:
                group = groups.setdefault(
                    key,
                    {
                        "name": key,
                        "selected": 0,
                        "scored": 0,
                        "pending": 0,
                        "failed": 0,
                        "source_ineligible": 0,
                        "sums": {},
                    },
                )
                group["selected"] += 1
                status = row["status"] or "pending"
                group[status] += 1
                if row["scores"]:
                    for name, value in json.loads(row["scores"]).items():
                        group["sums"][name] = group["sums"].get(name, 0) + value
    for group in groups.values():
        group["coverage"] = group["scored"] / group["selected"]
        group["means"] = {
            metric["name"]: group["sums"].get(metric["name"], 0) / group["scored"]
            if group["scored"]
            else None
            for metric in run["settings"]["metrics"]
        }
        del group["sums"]
    return {
        "groups": list(groups.values()),
        "partial": run["state"] in ("queued", "running", "canceling", "interrupted"),
    }


@router.get("/evaluations/{run_id}/inputs/{dataset_id}/{ordinal}")
@input_errors
def input_detail(run_id: str, dataset_id: str, ordinal: int, request: Request) -> dict[str, Any]:
    """Input detail."""
    store = request.app.state.evaluation_store
    run = store.run(run_id)
    with catalog_connection(store.root) as db:
        row = db.execute(
            "SELECT * FROM evaluation_inputs WHERE run_id=? AND dataset_id=? AND ordinal=?",
            (run_id, dataset_id, ordinal),
        ).fetchone()
        if row is None:
            raise KeyError("evaluation input not found")
        source = db.execute(
            "SELECT payload FROM inference_results WHERE run_id=? AND dataset_id=? AND ordinal=?",
            (run["source_inference_run_id"], dataset_id, ordinal),
        ).fetchone()
    try:
        example = store.catalog.evaluation_rows(dataset_id, offset=ordinal, limit=1)[0][
            2
        ].model_dump(mode="json")
    except (ValueError, OSError, IndexError, KeyError, UnknownDatasetError):
        example = None
    response = json.loads(source[0]) if source and row["source_result_present"] else None
    candidate = None
    candidate_error = None
    if response is not None and row["source_status"] == "ok":
        try:
            candidate = preprocess(response, run["settings"]["preprocess_source"])
        except (ProcessorError, ValueError) as exc:
            candidate_error = exc.message if isinstance(exc, ProcessorError) else str(exc)
    return {
        "available": example is not None
        and (not row["source_result_present"] or source is not None),
        "example": example,
        "response": response,
        "processed_response": candidate,
        "preprocess_error": candidate_error,
    }


class MethodTest(BaseModel):
    """Hold Method test fields."""

    source_inference_run_id: str
    dataset_id: str
    ordinal: int = Field(ge=0)
    method_id: str
    method_config: dict[str, Any] = Field(default_factory=dict)
    preprocess_source: str | None = None


def prepare_test(data: MethodTest, request: Request) -> tuple[Any, dict[str, Any], MethodContext]:
    """Prepare test."""
    store = request.app.state.evaluation_store
    method = METHODS.get(data.method_id)
    if method is None:
        raise ValueError("unknown evaluation method")
    config = method.resolve_config(data.method_config, store)
    rows = store.catalog.evaluation_rows(data.dataset_id, offset=data.ordinal, limit=1)
    if not rows:
        raise ValueError("selected example is unavailable")
    ordinal, source_index, example = rows[0]
    with catalog_connection(store.root) as db:
        row = db.execute(
            "SELECT payload FROM inference_results WHERE run_id=? AND dataset_id=? AND ordinal=?",
            (data.source_inference_run_id, data.dataset_id, ordinal),
        ).fetchone()
    if row is None:
        raise ValueError("source prediction is unavailable")
    response = json.loads(row[0])
    if response["status"] != "ok" or response["source_index"] != source_index:
        raise ValueError("source prediction is unsuccessful or misaligned")
    candidate = preprocess(response, data.preprocess_source)
    return (
        method,
        config,
        MethodContext(example, response, candidate, data.dataset_id, ordinal, source_index),
    )


@router.post("/evaluations/preview")
@input_errors
def preview_method(data: MethodTest, request: Request) -> dict[str, Any]:
    """Preview method."""
    method, config, context = prepare_test(data, request)
    result: dict[str, Any] = {
        "processed_response": context.candidate,
        "example": context.example.model_dump(mode="json"),
        "response": context.response,
    }
    if method.preview is not None:
        body = method.preview(config, context)
        result["request"] = body
        messages = body.get("messages")
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            result["rendered_prompt"] = messages[0].get("content")
    result["result_schema"] = method.result_schema(config)
    return result


@router.post("/evaluations/test-method")
async def test_method(data: MethodTest, request: Request) -> dict[str, Any]:
    """Test method."""
    try:
        method, config, context = prepare_test(data, request)
        admission = request.app.state.inference_runner.admission
        acquired = False
        if method.resource == "model_endpoint":
            acquired = admission.acquire(blocking=False)
            if not acquired:
                raise HTTPException(409, "model endpoint is busy")
        try:
            try:
                async with method.open(config, request.app.state.evaluation_store) as session:
                    outcome = await session.evaluate(context)
            except MethodFailure as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "evidence": exc.evidence,
                    "elapsed_ms": exc.elapsed_ms,
                    "attempts": exc.attempts,
                    "usage": exc.usage,
                }
            Draft202012Validator(method.result_schema(config)).validate(outcome.result)
            return {
                "processed_response": context.candidate,
                "result": outcome.result,
                "evidence": outcome.evidence,
                "elapsed_ms": outcome.elapsed_ms,
                "attempts": outcome.attempts,
                "usage": outcome.usage,
            }
        finally:
            if acquired:
                admission.release()
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from None
    except ProcessorError as exc:
        raise HTTPException(422, exc.message) from None


@router.post("/evaluations/method-schema")
@input_errors
def method_schema(data: MethodTest, request: Request) -> dict[str, Any]:
    """Resolve the selected method's result contract without calling a model."""
    method = METHODS.get(data.method_id)
    if method is None:
        raise ValueError("unknown evaluation method")
    config = method.resolve_config(data.method_config, request.app.state.evaluation_store)
    return method.result_schema(config)


class FieldCatalogRequest(BaseModel):
    """Selected source datasets whose prompt fields will be offered."""

    source_inference_run_id: str
    dataset_ids: list[str] = Field(min_length=1)


@router.post("/evaluations/fields")
@input_errors
def prompt_fields(data: FieldCatalogRequest, request: Request) -> list[str]:
    """Discover field names from bounded source snapshot pages."""
    store = request.app.state.evaluation_store
    fields = {
        "conversation",
        "response.content",
        "response.parsed",
        "response.tool_calls",
        "processed_response",
        "expected_output",
    }
    with catalog_connection(store.root) as db:
        for dataset_id in set(data.dataset_ids):
            dataset = db.execute(
                "SELECT rows_kept FROM inference_run_datasets WHERE run_id=? AND dataset_id=?",
                (data.source_inference_run_id, dataset_id),
            ).fetchone()
            if dataset is None:
                raise ValueError("selected dataset is not part of the source run")
            for offset in range(0, dataset["rows_kept"], 100):
                for _, _, example in store.catalog.evaluation_rows(
                    dataset_id, offset=offset, limit=100
                ):
                    fields.update(f"extras.{key}" for key in example.extras)
                    fields.update(f"segments.{key}" for key in example.segments)
    return sorted(fields)
