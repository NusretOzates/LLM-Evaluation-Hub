"""HTTP transport for bounded dataset previews and durable imports."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from llm_evaluation_hub.api.routes import repository
from llm_evaluation_hub.core.datasets.catalog import (
    DuplicateDatasetError,
    IdempotencyConflictError,
    UnknownTagError,
)
from llm_evaluation_hub.imports.contracts import (
    CreateImportRequest,
    Diagnostic,
    JobList,
    JobView,
    PreviewRequest,
    PreviewView,
    ProcessorView,
    SampleRequest,
    SampleView,
    SourcesView,
)
from llm_evaluation_hub.imports.jobs import ImportSupervisor, OperationError, validated_spec
from llm_evaluation_hub.imports.previews import PreviewService, SampleLookupError
from llm_evaluation_hub.imports.runtime import ProcessorError

router = APIRouter()
_IMPORT_PATHS = ("/dataset-source-samples", "/dataset-previews", "/dataset-imports")


def import_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Omit import payloads and validator context; preserve default errors elsewhere."""
    if not any(
        request.url.path == path or request.url.path.startswith(path + "/")
        for path in _IMPORT_PATHS
    ):
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})
    details = [
        {"loc": error["loc"], "msg": "Invalid request value.", "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


def _failure(error: Exception) -> HTTPException:
    """Map known domain failures and hide unexpected exception contents."""
    code = 422
    diagnostic = Diagnostic(category="operation", message="The import operation failed.")
    if isinstance(error, ProcessorError):
        code = {"busy": 429, "unavailable": 503, "interrupted": 503}.get(error.category, 422)
        diagnostic = Diagnostic(
            category=error.category,
            message=error.message,
            line=error.line,
            column=error.column,
            field_path=error.field_path,
            source_index=(
                error.source_index
                if isinstance(error, OperationError) and isinstance(error.source_index, int)
                else None
            ),
        )
    elif isinstance(error, SampleLookupError):
        code = 410 if error.expired else 404
        diagnostic = Diagnostic(
            category="expired" if error.expired else "not_found", message=str(error)
        )
    elif isinstance(error, (DuplicateDatasetError, IdempotencyConflictError)):
        code = 409
        diagnostic = Diagnostic(
            category="conflict",
            message="Dataset name or submission key conflicts with existing work.",
        )
    elif isinstance(error, UnknownTagError):
        diagnostic = Diagnostic(category="validation", message="An import tag no longer exists.")
    elif isinstance(error, KeyError):
        code = 404
        diagnostic = Diagnostic(category="not_found", message="Import job not found.")
    elif not isinstance(error, (ValidationError, ValueError)):
        code = 503
        diagnostic = Diagnostic(category="unavailable", message="Dataset imports are unavailable.")
    return HTTPException(status_code=code, detail=diagnostic.model_dump(mode="json"))


def _supervisor(request: Request) -> ImportSupervisor:
    """Read the typed lifecycle-owned supervisor from application state."""
    supervisor = getattr(request.app.state, "import_supervisor", None)
    if not isinstance(supervisor, ImportSupervisor):
        raise _failure(ProcessorError("unavailable", "Dataset imports are unavailable."))
    return supervisor


def _preview_service(request: Request) -> PreviewService:
    """Read the typed lifecycle-owned preview service from application state."""
    service = getattr(request.app.state, "preview_service", None)
    if not isinstance(service, PreviewService):
        raise _failure(ProcessorError("unavailable", "Dataset previews are unavailable."))
    return service


@router.get("/dataset-sources", response_model=SourcesView)
def sources() -> SourcesView:
    """Describe the enabled source and bounded import policy."""
    return SourcesView()


@router.post("/dataset-source-samples", response_model=SampleView)
def source_sample(body: SampleRequest, request: Request) -> SampleView:
    """Resolve and sample a source without publishing a dataset."""
    service = _preview_service(request)
    try:
        return service.sample(body)
    except Exception as error:
        raise _failure(error) from None


@router.post("/dataset-previews", response_model=PreviewView)
def preview(body: PreviewRequest, request: Request) -> PreviewView:
    """Preview cached rows and issue an attestation after successful validation."""
    service = _preview_service(request)
    try:
        return service.preview(body)
    except Exception as error:
        raise _failure(error) from None


@router.post("/dataset-imports", response_model=JobView, status_code=status.HTTP_202_ACCEPTED)
def submit(body: CreateImportRequest, request: Request) -> JobView:
    """Submit a current attestation, delegating replay and preflight to supervision."""
    supervisor = _supervisor(request)
    try:
        attestation = supervisor.store.get_preview(body.preview_id)
        if attestation is None:
            raise SampleLookupError(expired=False, resource="Processor preview")
        expiry = attestation["expires_at"]
        if not isinstance(expiry, str) or datetime.fromisoformat(expiry) <= datetime.now(UTC):
            # Expiry gates new work, not replay of an already accepted immutable job.
            replay = any(
                job["idempotency_key"] == body.idempotency_key
                for job in supervisor.store.list_jobs()
            )
            if not replay:
                raise SampleLookupError(expired=True, resource="Processor preview")
        spec = validated_spec(attestation["spec"]).model_copy(update={"tags": body.tags})
        return JobView.model_validate(supervisor.submit(body.name, spec, body.idempotency_key))
    except Exception as error:
        raise _failure(error) from None


@router.get("/dataset-imports", response_model=JobList)
def list_imports(request: Request) -> JobList:
    """Rediscover persisted import history."""
    supervisor = _supervisor(request)
    try:
        return JobList(jobs=[JobView.model_validate(item) for item in supervisor.list_jobs()])
    except Exception as error:
        raise _failure(error) from None


@router.get("/dataset-imports/{job_id}", response_model=JobView)
def get_import(job_id: str, request: Request) -> JobView:
    """Read authoritative progress without waiting for heavy operations."""
    supervisor = _supervisor(request)
    try:
        return JobView.model_validate(supervisor.get_job(job_id))
    except Exception as error:
        raise _failure(error) from None


@router.post("/dataset-imports/{job_id}/cancel", response_model=JobView)
def cancel_import(job_id: str, request: Request) -> JobView:
    """Request cancellation and return its authoritative acknowledgement."""
    supervisor = _supervisor(request)
    try:
        return JobView.model_validate(supervisor.cancel(job_id))
    except Exception as error:
        raise _failure(error) from None


@router.get("/datasets/{dataset_id}/processor", response_model=ProcessorView)
def processor(dataset_id: str, request: Request) -> ProcessorView:
    """Read optional processor provenance from an immutable snapshot."""
    return ProcessorView.model_validate(
        {"provenance": repository(request).get_processor(dataset_id)}
    )
