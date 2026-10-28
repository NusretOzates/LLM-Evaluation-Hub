"""Trust boundaries and immutable dataset identity through real HTTP routes."""

import sqlite3
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient
from tests.datasets.catalog.memory import MemorySource

from llm_evaluation_hub.api import create_app
from llm_evaluation_hub.core.datasets.catalog import DatasetRepository
from llm_evaluation_hub.core.datasets.records import ProcessedExample


@pytest.mark.parametrize("name", ["team/cases", "Türkçe %?#", "__proto__"])
def test_id_routes_round_trip_any_display_name(tmp_path: Path, name: str) -> None:
    root = tmp_path / "catalog"
    repo = DatasetRepository(root)
    repo.create_tag("__proto__")
    record = repo.register(
        name,
        MemorySource(pl.DataFrame({"text": ["alpha"]})),
        lambda row: ProcessedExample(conversation=[{"role": "user", "content": str(row["text"])}]),
        processor_id="tests.identity",
    )
    with TestClient(create_app(root)) as client:
        endpoint = f"/dataset-ids/{record.id}"
        assert client.get(endpoint).json()["name"] == name
        assert client.get(f"{endpoint}/examples").json()["total"] == 1
        assert client.post(f"{endpoint}/tags", json={"paths": ["__proto__"]}).json()["tags"] == [
            "__proto__"
        ]
        assert (
            client.request("DELETE", f"{endpoint}/tags", json={"paths": ["__proto__"]}).json()[
                "tags"
            ]
            == []
        )
        assert client.get("/dataset-ids/missing").status_code == 404
        assert client.get(f"{endpoint}/examples?limit=101").status_code == 422


def test_cors_requires_an_explicit_origin(tmp_path: Path) -> None:
    headers = {"Origin": "https://unrelated.example", "Access-Control-Request-Method": "POST"}
    with TestClient(create_app(tmp_path / "default")) as client:
        assert "access-control-allow-origin" not in client.get("/datasets", headers=headers).headers
        assert "access-control-allow-origin" not in client.options("/tags", headers=headers).headers
    with TestClient(
        create_app(tmp_path / "explicit", allowed_origins=("http://localhost:5173",))
    ) as client:
        assert client.options("/tags", headers=headers).status_code == 400
        allowed = {
            **headers,
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Headers": "content-type",
        }
        response = client.options("/tags", headers=allowed)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_corrupt_metadata_is_not_reported_as_client_validation(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    repo = DatasetRepository(root)
    record = repo.register(
        "cases",
        MemorySource(pl.DataFrame({"text": ["alpha"]})),
        lambda row: ProcessedExample(conversation=[{"role": "user", "content": str(row["text"])}]),
        processor_id="tests.corrupt",
    )
    with sqlite3.connect(root / "catalog.sqlite") as connection:
        connection.execute("UPDATE datasets SET segment_keys = 'invalid secret data'")
    with TestClient(create_app(root), raise_server_exceptions=False) as client:
        response = client.get(f"/dataset-ids/{record.id}")
        assert response.status_code == 500
        assert "secret" not in response.text


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "http://*",
        "http://localhost/path",
        "http://localhost:bad",
        "http://localhost:99999",
        "http://user:pass@localhost",
        "https://example.test#fragment",
    ],
)
def test_invalid_origin_configuration_fails_before_creating_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    from llm_evaluation_hub.api.asgi import app

    root = tmp_path / "uncreated"
    monkeypatch.setenv("LLM_EVAL_CATALOG", str(root))
    monkeypatch.setenv("LLM_EVAL_ORIGINS", origin)
    with pytest.raises(ValueError, match="LLM_EVAL_ORIGINS"):
        app()
    assert not root.exists()
