"""FastAPI application for the dataset catalog."""

import logging
import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from polars.exceptions import PolarsError

from llm_evaluation_hub.api.import_routes import import_validation_error
from llm_evaluation_hub.api.import_routes import router as import_router
from llm_evaluation_hub.api.inference_routes import router as inference_router
from llm_evaluation_hub.api.routes import router
from llm_evaluation_hub.api.schemas import InvalidRequestError
from llm_evaluation_hub.core.datasets.catalog import (
    DatasetRepository,
    DuplicateTagError,
    UnknownDatasetError,
    UnknownTagError,
)
from llm_evaluation_hub.core.datasets.catalog.errors import DatasetInUseError
from llm_evaluation_hub.imports.jobs import ImportSupervisor
from llm_evaluation_hub.imports.previews import PreviewService
from llm_evaluation_hub.imports.sources import SourceAdapter
from llm_evaluation_hub.inference.runner import Runner
from llm_evaluation_hub.inference.store import InferenceStore

logger = logging.getLogger(__name__)


def create_app(
    catalog_root: Path,
    *,
    allowed_origins: tuple[str, ...] = (),
    source_adapter: SourceAdapter | None = None,
) -> FastAPI:
    """Serve the catalog stored at `catalog_root`."""
    supervisor = ImportSupervisor(catalog_root, source_adapter=source_adapter)
    inference_store = InferenceStore(catalog_root)
    inference_runner = Runner(inference_store)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        del app
        supervisor.start()
        try:
            inference_runner.start()
            try:
                yield
            finally:
                inference_runner.stop()
        finally:
            supervisor.stop()

    application = FastAPI(title="LLM Evaluation Hub", lifespan=lifespan)
    application.state.inference_store = inference_store
    application.state.inference_runner = inference_runner
    application.state.import_supervisor = supervisor
    application.state.preview_service = PreviewService(supervisor.store, supervisor)

    @application.exception_handler(RequestValidationError)
    def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return import_validation_error(request, exc)

    application.state.repository = DatasetRepository(catalog_root)
    if allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Content-Type"],
        )
    application.include_router(router)
    application.include_router(import_router)
    application.include_router(inference_router)
    _register_errors(application)
    logger.info("Serving catalog at %s", catalog_root)
    return application


def _register_errors(application: FastAPI) -> None:
    """Map catalog failures to HTTP status codes."""

    @application.exception_handler(UnknownDatasetError)
    def unknown_dataset(request: Request, exc: UnknownDatasetError) -> JSONResponse:
        del request  # FastAPI supplies the request to every exception handler.
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(UnknownTagError)
    def unknown_tag(request: Request, exc: UnknownTagError) -> JSONResponse:
        del request  # FastAPI supplies the request to every exception handler.
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(DatasetInUseError)
    def dataset_in_use(request: Request, exc: DatasetInUseError) -> JSONResponse:
        del request
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.exception_handler(DuplicateTagError)
    def duplicate_tag(request: Request, exc: DuplicateTagError) -> JSONResponse:
        del request
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.exception_handler(InvalidRequestError)
    def invalid_value(request: Request, exc: InvalidRequestError) -> JSONResponse:
        del request  # FastAPI supplies the request to every exception handler.
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def storage_failure(request: Request, exc: Exception) -> JSONResponse:
        # Never include validation payloads or raw conversation data in diagnostics.
        logger.error(
            "Catalog storage failure: %s %s (%s)",
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500, content={"detail": "The catalog storage could not be read."}
        )

    for error in (ValueError, sqlite3.Error, OSError, PolarsError):
        application.add_exception_handler(error, storage_failure)
