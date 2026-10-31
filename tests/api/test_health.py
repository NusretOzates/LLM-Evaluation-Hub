"""Lightweight health checks must not depend on catalog access."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_evaluation_hub.api.routes import router


def test_health_without_a_catalog() -> None:
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
