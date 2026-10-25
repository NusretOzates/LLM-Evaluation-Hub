"""Hugging Face source loading without a network call."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from llm_evaluation_hub.datasets.catalog import DatasetRepository
from llm_evaluation_hub.datasets.records import ProcessedExample
from llm_evaluation_hub.datasets.sources.hf import HfDatasetSource


def _processor(row: dict[str, object]) -> ProcessedExample:
    label = row["label"]
    if not isinstance(label, str):
        raise TypeError("label must be a string")
    return ProcessedExample(
        conversation=[{"role": "user", "content": str(row["text"])}],
        expected_output=label,
        segments={"language": str(row["language"])},
    )


def test_hf_source_uses_the_environment_token_and_a_split_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "hf-env-token-do-not-store"
    monkeypatch.setenv("HF_TOKEN", token)
    captured: dict[str, object] = {}

    def fake_dataset_info(
        self: object,
        repo_id: str,
        *,
        revision: str | None = None,
        token: str | None = None,
        **kwargs: object,
    ) -> SimpleNamespace:
        del self, repo_id, revision, kwargs
        captured["token"] = token
        return SimpleNamespace(sha="b" * 40)

    def fake_load(path: str, **kwargs: object) -> object:
        del path
        captured["split"] = kwargs["split"]
        from datasets import Dataset

        return Dataset.from_list([{"text": "Merhaba", "label": "greeting", "language": "tr"}])

    monkeypatch.setattr(
        "llm_evaluation_hub.datasets.sources.hf.HfApi.dataset_info",
        fake_dataset_info,
    )
    monkeypatch.setattr("llm_evaluation_hub.datasets.sources.hf.load_dataset", fake_load)
    source = HfDatasetSource("org/cases", "train")

    frame = source.read(limit=1)

    assert captured["token"] == token
    assert captured["split"] == "train[:1]"
    assert frame.height == 1
    assert token not in source.describe().model_dump_json()
    with pytest.raises(ValueError, match="plain split"):
        HfDatasetSource("org/cases", "train[:10]").read(limit=1)


def test_hf_source_loads_a_local_fixture_and_stores_the_stubbed_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = tmp_path / "rows.json"
    fixture.write_text(
        "\n".join(
            [
                json.dumps({"text": "Merhaba", "label": "greeting", "language": "tr"}),
                json.dumps({"text": "Hello", "label": "greeting", "language": "en"}),
            ]
        ),
        encoding="utf-8",
    )
    token = "hf-test-token-do-not-store"
    captured: dict[str, object] = {}

    def fake_dataset_info(
        self: object,
        repo_id: str,
        *,
        revision: str | None = None,
        token: str | None = None,
        **kwargs: object,
    ) -> SimpleNamespace:
        del self, kwargs
        captured["info"] = {"repo_id": repo_id, "revision": revision, "token": token}
        return SimpleNamespace(sha="a" * 40)

    def fake_load(path: str, **kwargs: object) -> object:
        captured["load"] = {"path": path, **kwargs}
        from datasets import load_dataset

        return load_dataset("json", data_files=str(fixture), split="train")

    monkeypatch.setattr(
        "llm_evaluation_hub.datasets.sources.hf.HfApi.dataset_info",
        fake_dataset_info,
    )
    monkeypatch.setattr("llm_evaluation_hub.datasets.sources.hf.load_dataset", fake_load)

    source = HfDatasetSource(
        "org/cases",
        "train",
        config="subset",
        revision="main-ref",
        token=token,
    )
    repository = DatasetRepository(tmp_path / "catalog")
    repository.create_tag("Trendyol Cases")
    record = repository.register(
        "cases",
        source,
        _processor,
        processor_id="tests.hf",
        tags=["Trendyol Cases"],
        segments=["language"],
    )

    assert captured["info"] == {
        "repo_id": "org/cases",
        "revision": "main-ref",
        "token": token,
    }
    assert captured["load"] == {
        "path": "org/cases",
        "name": "subset",
        "split": "train",
        "revision": "a" * 40,
        "token": token,
    }
    assert record.resolved_sha == "a" * 40
    assert record.source_type == "hf_dataset"
    assert record.repo_id == "org/cases"
    assert record.split == "train"
    assert repository.rows("cases").get_column("language").to_list() == ["tr", "en"]
    catalog_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (tmp_path / "catalog").rglob("*")
        if path.is_file()
    )
    assert token not in catalog_text
