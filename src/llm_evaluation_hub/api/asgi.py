"""Uvicorn entrypoint for the catalog API."""

import logging
import os
from pathlib import Path

from fastapi import FastAPI

from llm_evaluation_hub.api.app import create_app
from llm_evaluation_hub.api.seed import ensure_starter_catalog

logger = logging.getLogger(__name__)


def app() -> FastAPI:
    """Build the app from `LLM_EVAL_CATALOG`, or `data/catalog` when unset.

    When `LLM_EVAL_SEED` is a non-empty path, that catalog is copied into the
    target only if `catalog.sqlite` is not already there.
    """
    root = Path(os.environ.get("LLM_EVAL_CATALOG", "data/catalog"))
    seed = os.environ.get("LLM_EVAL_SEED", "").strip()
    if seed:
        if ensure_starter_catalog(root, Path(seed)):
            logger.info("Published starter catalog into %s", root)
        else:
            logger.info("Keeping existing catalog at %s", root)
    return create_app(root)
