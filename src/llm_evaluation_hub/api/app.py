"""FastAPI application for the dataset catalog."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from llm_evaluation_hub.api.routes import router
from llm_evaluation_hub.core.datasets.catalog import (
    DatasetRepository,
    UnknownDatasetError,
    UnknownTagError,
)

logger = logging.getLogger(__name__)


def create_app(catalog_root: Path) -> FastAPI:
    """Serve the catalog stored at `catalog_root`."""
    application = FastAPI(title="LLM Evaluation Hub")
    application.state.repository = DatasetRepository(catalog_root)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
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

    @application.exception_handler(ValueError)
    def invalid_value(request: Request, exc: ValueError) -> JSONResponse:
        del request  # FastAPI supplies the request to every exception handler.
        return JSONResponse(status_code=422, content={"detail": str(exc)})
