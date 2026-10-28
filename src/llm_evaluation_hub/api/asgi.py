"""Uvicorn entrypoint for the catalog API."""

import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI

from llm_evaluation_hub.api.app import create_app
from llm_evaluation_hub.api.seed import ensure_starter_catalog

logger = logging.getLogger(__name__)


def app() -> FastAPI:
    """Build the app from `LLM_EVAL_CATALOG`, or `data/catalog` when unset.

    When `LLM_EVAL_SEED` is a non-empty path, that catalog is copied into the
    target only if `catalog.sqlite` is not already there.
    """
    origins = tuple(
        value.strip()
        for value in os.environ.get("LLM_EVAL_ORIGINS", "").split(",")
        if value.strip()
    )
    for origin in origins:
        parsed = urlsplit(origin)
        try:
            _ = parsed.port
        except ValueError as error:
            raise ValueError("LLM_EVAL_ORIGINS contains an invalid port") from error
        if (
            "*" in origin
            or any(char.isspace() for char in origin)
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("LLM_EVAL_ORIGINS must contain explicit HTTP origins without paths")
    root = Path(os.environ.get("LLM_EVAL_CATALOG", "data/catalog"))
    seed = os.environ.get("LLM_EVAL_SEED", "").strip()
    if seed:
        if ensure_starter_catalog(root, Path(seed)):
            logger.info("Published starter catalog into %s", root)
        else:
            logger.info("Keeping existing catalog at %s", root)
    return create_app(root, allowed_origins=origins)
