"""Dataset inspection routes."""

from pathlib import Path

import polars as pl
from fastapi.testclient import TestClient
from tests.datasets.catalog.memory import MemorySource

from llm_evaluation_hub.datasets.catalog import DatasetRepository
from llm_evaluation_hub.datasets.records import ProcessedExample


def _processor(row: dict[str, object]) -> ProcessedExample | None:
    text = str(row["text"])
    if text == "":
        return None
    return ProcessedExample(
        conversation=[{"role": "user", "content": text}],
        expected_output=text,
        segments={"language": "tr"},
    )


def _seed(root: Path) -> None:
    repository = DatasetRepository(root)
    repository.ensure_path(["Trendyol Cases", "classification"])
    repository.ensure_path(["Language", "Turkish"])
    source = MemorySource(
        pl.DataFrame({"text": ["alpha", "beta", "gamma", ""]}),
    )

    repository.register(
        "classification-cases",
        source,
        _processor,
        processor_id="tests.classify",
        tags=["Trendyol Cases/classification"],
        segments=["language"],
    )
    repository.register(
        "turkish-only",
        source,
        _processor,
        processor_id="tests.classify",
        tags=["Language/Turkish"],
        segments=["language"],
    )


def test_list_returns_inspection_metadata(catalog_root: Path, client: TestClient) -> None:
    _seed(catalog_root)

    listed = client.get("/datasets")
    filtered = client.get("/datasets", params={"tag": "Trendyol Cases"})
    one = client.get("/datasets/classification-cases")

    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["classification-cases", "turkish-only"]
    body = one.json()
    assert one.status_code == 200
    assert body == listed.json()[0]
    assert "parquet_path" not in body
    assert body["created_at"]
    assert body["source_type"] == "memory"
    assert body["rows_loaded"] == 4
    assert body["rows_kept"] == 3
    assert body["rows_dropped"] == 1
    assert body["segment_keys"] == ["language"]
    assert body["tags"] == ["Trendyol Cases/classification"]
    assert [item["name"] for item in filtered.json()] == ["classification-cases"]


def test_tag_links_follow_the_dataset(catalog_root: Path, client: TestClient) -> None:
    _seed(catalog_root)

    linked = client.post(
        "/datasets/classification-cases/tags",
        json={"paths": ["Language/Turkish"]},
    )
    removed = client.request(
        "DELETE",
        "/datasets/classification-cases/tags",
        json={"paths": ["Trendyol Cases/classification"]},
    )

    assert linked.status_code == 200
    assert linked.json()["tags"] == ["Language/Turkish", "Trendyol Cases/classification"]
    assert removed.status_code == 200
    assert removed.json()["tags"] == ["Language/Turkish"]
    repeated = client.post(
        "/datasets/classification-cases/tags",
        json={"paths": ["Language/Turkish"]},
    )
    absent = client.request(
        "DELETE",
        "/datasets/classification-cases/tags",
        json={"paths": ["Trendyol Cases/classification"]},
    )
    assert repeated.status_code == 200
    assert repeated.json()["tags"] == ["Language/Turkish"]
    assert absent.status_code == 200
    assert absent.json()["tags"] == ["Language/Turkish"]
    assert client.get("/datasets/missing").status_code == 404
    assert client.get("/datasets", params={"tag": "Missing"}).status_code == 404
    assert (
        client.post("/datasets/classification-cases/tags", json={"paths": ["Missing"]}).status_code
        == 404
    )


def test_examples_are_paged(catalog_root: Path, client: TestClient) -> None:
    _seed(catalog_root)

    first = client.get("/datasets/classification-cases/examples", params={"offset": 0, "limit": 1})
    second = client.get("/datasets/classification-cases/examples", params={"offset": 1, "limit": 1})
    past_end = client.get(
        "/datasets/classification-cases/examples",
        params={"offset": 10, "limit": 1},
    )
    too_large = client.get("/datasets/classification-cases/examples", params={"limit": 101})

    assert first.status_code == 200
    page = first.json()
    assert page["total"] == 3
    assert page["offset"] == 0
    assert page["limit"] == 1
    assert page["examples"][0]["conversation"][1]["content"] == "alpha"
    assert second.json()["examples"][0]["conversation"][1]["content"] == "beta"
    assert past_end.json()["examples"] == []
    assert too_large.status_code == 422
    assert (
        client.get("/datasets/classification-cases/examples", params={"limit": 0}).status_code
        == 422
    )
    assert client.get("/datasets/missing/examples").status_code == 404
