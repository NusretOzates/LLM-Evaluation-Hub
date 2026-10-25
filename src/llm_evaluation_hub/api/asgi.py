"""Uvicorn entrypoint for the catalog API."""

import os
from pathlib import Path

from fastapi import FastAPI

from llm_evaluation_hub.api.app import create_app


def app() -> FastAPI:
    """Build the app from `LLM_EVAL_CATALOG`, or `data/catalog` when unset."""
    root = Path(os.environ.get("LLM_EVAL_CATALOG", "data/catalog"))
    return create_app(root)
