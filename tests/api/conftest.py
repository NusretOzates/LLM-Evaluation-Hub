"""API test fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from llm_evaluation_hub.api import create_app


@pytest.fixture
def catalog_root(tmp_path: Path) -> Path:
    return tmp_path / "catalog"


@pytest.fixture
def client(catalog_root: Path) -> Iterator[TestClient]:
    with TestClient(create_app(catalog_root)) as test_client:
        yield test_client
