"""Tag forest rules."""

from pathlib import Path

import polars as pl
import pytest
from tests.datasets.catalog.memory import MemorySource

from llm_evaluation_hub.core.datasets.catalog import (
    DatasetRepository,
    DuplicateTagError,
    TagInUseError,
    UnknownTagError,
)
from llm_evaluation_hub.core.datasets.records import ProcessedExample


def _repository(tmp_path: Path) -> DatasetRepository:
    return DatasetRepository(tmp_path / "catalog")


def _example(text: str) -> ProcessedExample:
    return ProcessedExample(conversation=[{"role": "user", "content": text}])


def _source() -> MemorySource:
    return MemorySource(pl.DataFrame({"text": ["one", "two"]}))


def test_list_tags_returns_each_node_with_its_parent_path(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create_tag("Language")
    repository.create_tag("Trendyol Cases")
    repository.create_tag("Turkish", parent="Language")
    repository.create_tag("Summarization", parent="Trendyol Cases")

    assert [(tag.path, tag.parent) for tag in repository.list_tags()] == [
        ("Language", None),
        ("Language/Turkish", "Language"),
        ("Trendyol Cases", None),
        ("Trendyol Cases/Summarization", "Trendyol Cases"),
    ]


def test_ensure_path_creates_a_chain_and_reuses_existing_nodes(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    leaf, created = repository.ensure_path(
        ["Trendyol Cases", "Summarization", "Review Summarization"]
    )
    again, created_again = repository.ensure_path(
        ["Trendyol Cases", "Summarization", "Review Summarization"]
    )
    sibling, sibling_created = repository.ensure_path(
        ["Trendyol Cases", "Summarization", "Chat Summarization"]
    )

    assert created is True
    assert leaf.path == "Trendyol Cases/Summarization/Review Summarization"
    assert leaf.parent == "Trendyol Cases/Summarization"
    assert created_again is False
    assert again == leaf
    assert sibling_created is True
    assert sibling.path == "Trendyol Cases/Summarization/Chat Summarization"
    assert [tag.path for tag in repository.list_tags()] == [
        "Trendyol Cases",
        "Trendyol Cases/Summarization",
        "Trendyol Cases/Summarization/Chat Summarization",
        "Trendyol Cases/Summarization/Review Summarization",
    ]


def test_ensure_paths_rolls_back_every_path_when_one_segment_is_rejected(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with pytest.raises(ValueError, match="/"):
        repository.ensure_paths(
            [["Trendyol Cases", "Summarization"], ["Trendyol Cases", "bad/name"]]
        )

    assert repository.list_tags() == []


def test_ensure_path_rolls_back_when_a_later_segment_is_rejected(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with pytest.raises(ValueError, match="empty"):
        repository.ensure_path([])
    with pytest.raises(ValueError, match="/"):
        repository.ensure_path(["Trendyol Cases", "bad/name"])

    assert repository.list_tags() == []


def test_tag_tree_keeps_sibling_names_unique_and_child_names_reusable(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create_tag("Trendyol Cases")
    repository.create_tag("classification", parent="Trendyol Cases")
    repository.create_tag("Language")
    turkish = repository.create_tag("Turkish", parent="Language")
    classification = repository.create_tag("classification", parent="Language")

    assert turkish.path == "Language/Turkish"
    assert classification.path == "Language/classification"
    with pytest.raises(DuplicateTagError):
        repository.create_tag("classification", parent="Trendyol Cases")
    with pytest.raises(UnknownTagError):
        repository.create_tag("Turkish", parent="Missing")
    with pytest.raises(ValueError, match="/"):
        repository.create_tag("bad/name")


def test_listing_a_parent_includes_datasets_tagged_with_a_descendant(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create_tag("Trendyol Cases")
    repository.create_tag("classification", parent="Trendyol Cases")
    repository.create_tag("Language")
    repository.create_tag("Turkish", parent="Language")
    source = _source()

    def processor(row: dict[str, object]) -> ProcessedExample:
        return _example(str(row["text"]))

    repository.register(
        "classification-cases",
        source,
        processor,
        processor_id="tests.classify",
        tags=["Trendyol Cases/classification"],
    )
    repository.register(
        "turkish-only",
        source,
        processor,
        processor_id="tests.classify",
        tags=["Language/Turkish"],
    )

    repository.add_tags("classification-cases", ["Trendyol Cases"])
    names = [record.name for record in repository.list_datasets(tag="Trendyol Cases")]
    assert names == ["classification-cases"]
    direct = repository.get("classification-cases")
    assert direct.tags == ["Trendyol Cases", "Trendyol Cases/classification"]
    parent_only = repository.register(
        "parent-only",
        source,
        processor,
        processor_id="tests.classify",
        tags=["Trendyol Cases"],
    )
    assert parent_only.tags == ["Trendyol Cases"]
    listed = [record.name for record in repository.list_datasets(tag="Trendyol Cases")]
    assert listed == ["classification-cases", "parent-only"]


def test_add_and_remove_tags_change_only_the_links(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create_tag("Trendyol Cases")
    repository.create_tag("classification", parent="Trendyol Cases")
    repository.create_tag("summarization", parent="Trendyol Cases")
    repository.create_tag("Language")
    repository.create_tag("Turkish", parent="Language")
    source = MemorySource(pl.DataFrame({"text": ["one"]}))

    def processor(row: dict[str, object]) -> ProcessedExample:
        return _example(str(row["text"]))

    repository.register(
        "cases",
        source,
        processor,
        processor_id="tests.classify",
        tags=["Trendyol Cases/classification", "Language/Turkish"],
    )
    repository.add_tags("cases", ["Trendyol Cases/summarization", "Language/Turkish"])
    repository.remove_tags("cases", ["Language/Turkish"])

    assert repository.get("cases").tags == [
        "Trendyol Cases/classification",
        "Trendyol Cases/summarization",
    ]
    with pytest.raises(TagInUseError):
        repository.delete_tag("Trendyol Cases")
    repository.remove_tags(
        "cases",
        ["Trendyol Cases/classification", "Trendyol Cases/summarization"],
    )
    repository.delete_tag("Trendyol Cases/classification")
    repository.delete_tag("Trendyol Cases/summarization")
    repository.delete_tag("Trendyol Cases")
