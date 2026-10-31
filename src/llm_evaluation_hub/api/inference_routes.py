"""Inference configuration and run endpoints."""

from collections.abc import Callable
from functools import wraps
from typing import Annotated, ParamSpec, TypeVar

from fastapi import APIRouter, HTTPException, Query, Request
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, Field

from llm_evaluation_hub.core.datasets.records import ProcessedExample
from llm_evaluation_hub.inference.compiler import compile_request
from llm_evaluation_hub.inference.contracts import (
    ConnectionProfile,
    Generation,
    OutputFormat,
    ResultPage,
    RowResult,
    RunSpec,
    RunView,
)

router = APIRouter()

P = ParamSpec("P")
T = TypeVar("T")


def input_errors[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    """Map configuration errors without exposing unrelated storage failures."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from None
        except (ValueError, SchemaError) as exc:
            raise HTTPException(422, str(exc)) from None

    return wrapped


@router.get("/connections")
def profiles(request: Request) -> list[ConnectionProfile]:
    """List saved connections."""
    return request.app.state.inference_store.profiles()


@router.post("/connections")
@input_errors
def save_profile(profile: ConnectionProfile, request: Request) -> ConnectionProfile:
    """Create or update a connection."""
    return request.app.state.inference_store.save_profile(profile)


@router.get("/connections/{profile_id}")
@input_errors
def get_profile(profile_id: str, request: Request) -> ConnectionProfile:
    """Read one saved connection."""
    return request.app.state.inference_store.profile(profile_id)


@router.put("/connections/{profile_id}")
@input_errors
def update_profile(
    profile_id: str, profile: ConnectionProfile, request: Request
) -> ConnectionProfile:
    """Update an existing connection by immutable identity."""
    store = request.app.state.inference_store
    store.profile(profile_id)
    if profile.id and profile.id != profile_id:
        raise HTTPException(422, "profile ID does not match the path")
    return store.save_profile(profile.model_copy(update={"id": profile_id}))


@router.delete("/connections/{profile_id}", status_code=204)
def delete_profile(profile_id: str, request: Request) -> None:
    """Remove a connection."""
    request.app.state.inference_store.delete_profile(profile_id)


@router.get("/dataset-ids/{dataset_id}/output-format")
@input_errors
def output_format(dataset_id: str, request: Request) -> OutputFormat:
    """Read output metadata."""
    return request.app.state.inference_store.output(dataset_id)


@router.put("/dataset-ids/{dataset_id}/output-format")
@input_errors
def save_output_format(dataset_id: str, output: OutputFormat, request: Request) -> OutputFormat:
    """Update output metadata."""
    return request.app.state.inference_store.save_output(dataset_id, output)


class InferenceExampleRequest(BaseModel):
    """Settings and row for a credential-free request preview."""

    profile_id: str
    dataset_id: str
    ordinal: int = 0
    generation: Generation = Generation()
    output: OutputFormat = OutputFormat()
    timeout_seconds: float = Field(default=120, gt=0)
    retries: int = Field(default=2, ge=0, le=10)
    rpm: int = Field(default=60, ge=1)


@router.post("/inference/preview")
@input_errors
def preview(body: InferenceExampleRequest, request: Request) -> dict:
    """Compile a selected row without contacting an endpoint."""
    store = request.app.state.inference_store
    rows = store.catalog.inference_rows(body.dataset_id, offset=body.ordinal, limit=1)
    if not rows:
        raise HTTPException(404, "row not found")
    return compile_request(store.profile(body.profile_id), body.generation, body.output, rows[0][2])


@router.post("/inference/runs", status_code=201)
@input_errors
def create_run(spec: RunSpec, request: Request) -> RunView:
    """Preflight and queue a run."""
    return request.app.state.inference_store.create(spec)


@router.get("/inference/runs")
def list_runs(request: Request) -> list[RunView]:
    """List inference runs."""
    return request.app.state.inference_store.runs()


@router.get("/inference/runs/{run_id}")
@input_errors
def get_run(run_id: str, request: Request) -> RunView:
    """Read one run."""
    return request.app.state.inference_store.run(run_id)


@router.get("/inference/runs/{run_id}/results")
@input_errors
def results(
    run_id: str,
    request: Request,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    dataset_id: str | None = None,
    errors_only: bool = False,
) -> ResultPage:
    """Read a filtered result page."""
    return request.app.state.inference_store.results(
        run_id, offset, limit, dataset_id=dataset_id, errors_only=errors_only
    )


@router.post("/inference/runs/{run_id}/cancel", status_code=204)
def cancel(run_id: str, request: Request) -> None:
    """Stop dispatch and active requests."""
    request.app.state.inference_runner.cancel(run_id)


@router.post("/inference/runs/{run_id}/resume", status_code=204)
@input_errors
def resume(run_id: str, request: Request) -> None:
    """Explicitly resume interrupted work."""
    request.app.state.inference_runner.resume(run_id)


@router.post("/inference/test")
async def test_example(body: InferenceExampleRequest, request: Request) -> RowResult:
    """Send one explicit example with the same transport as a run."""
    import os

    from openai import AsyncOpenAI

    from llm_evaluation_hub.inference.runner import RateLimiter
    from llm_evaluation_hub.inference.transport import AuthenticationFailure, send

    runner = request.app.state.inference_runner
    if not runner.admission.acquire(blocking=False):
        raise HTTPException(409, "tests are unavailable while a run is active")
    try:
        store = request.app.state.inference_store
        try:
            profile = store.profile(body.profile_id)
        except KeyError:
            raise HTTPException(404, "profile not found") from None
        key = os.environ.get(profile.api_key_env) if profile.api_key_env else "unused"
        if not key:
            raise HTTPException(422, "configured API key environment variable is missing")
        payload = preview(body, request)
        rows = store.catalog.inference_rows(body.dataset_id, offset=body.ordinal, limit=1)
        result = RowResult(
            dataset_id=body.dataset_id,
            ordinal=body.ordinal,
            source_index=rows[0][1],
            status="error",
        )
        async with AsyncOpenAI(base_url=profile.base_url, api_key=key, max_retries=0) as client:
            try:
                return await send(
                    client,
                    payload,
                    body.output,
                    result,
                    timeout=body.timeout_seconds,
                    retries=body.retries,
                    limiter=RateLimiter(body.rpm),
                    omit_auth=profile.api_key_env is None,
                )
            except AuthenticationFailure:
                raise HTTPException(502, "endpoint authentication failed") from None
    finally:
        runner.admission.release()


class InferenceInput(BaseModel):
    """A retained source row while its snapshot remains available."""

    ordinal: int
    source_index: int
    example: ProcessedExample


@router.get("/inference/runs/{run_id}/datasets/{dataset_id}/inputs/{ordinal}")
@input_errors
def run_input(run_id: str, dataset_id: str, ordinal: int, request: Request) -> InferenceInput:
    """Read a run's input by retained ordinal, including trashed snapshots."""
    store = request.app.state.inference_store
    run = store.run(run_id)
    dataset = next((item for item in run.datasets if item.id == dataset_id), None)
    if dataset is None or ordinal < 0 or ordinal >= dataset.rows or not dataset.input_available:
        raise HTTPException(404, "input is unavailable")
    rows = store.catalog.inference_rows(dataset_id, offset=ordinal, limit=1)
    if not rows:
        raise HTTPException(404, "input is unavailable")
    retained, source_index, example = rows[0]
    return InferenceInput(ordinal=retained, source_index=source_index, example=example)
