"""HTTP contract regressions for source capabilities and new import declarations."""

import pytest
from pydantic import ValidationError

from llm_evaluation_hub.imports.contracts import (
    CreateImportRequest,
    PreviewRequest,
    SampleRequest,
    SourceSpec,
)


@pytest.mark.parametrize(
    "repo_id",
    ["/etc/passwd", "../catalog", "https://example.com/data", "file:///tmp/data", r"C:\data"],
)
def test_source_rejects_paths_and_urls(repo_id: str) -> None:
    with pytest.raises(ValueError):
        SourceSpec(repo_id=repo_id)


def test_source_accepts_hub_coordinates_and_pinned_revision() -> None:
    source = SourceSpec(repo_id="organization/dataset", config="default", revision="refs/pr/1")
    assert source.kind == "hf_dataset"
    assert source.split == "train"
    assert source.revision == "refs/pr/1"


@pytest.mark.parametrize("split", ["train[:10]", "train/test", "", " train"])
def test_source_rejects_split_expressions(split: str) -> None:
    with pytest.raises(ValidationError):
        SourceSpec(repo_id="organization/dataset", split=split)


@pytest.mark.parametrize("limit", [0, 10_001])
def test_source_limit_is_enforced_before_loading(limit: int) -> None:
    with pytest.raises(ValidationError):
        SampleRequest(source=SourceSpec(repo_id="organization/dataset"), row_limit=limit)


def test_new_tools_segment_is_rejected_without_changing_legacy_records() -> None:
    with pytest.raises(ValidationError, match="tools"):
        PreviewRequest(sample_id="sample", source_code="None", segment_keys=["tools"])


def test_submission_name_is_normalized_and_unknown_inputs_rejected() -> None:
    request = CreateImportRequest(preview_id="preview", name="  cases  ", idempotency_key="submit")
    assert request.name == "cases"
    with pytest.raises(ValidationError):
        CreateImportRequest.model_validate(
            {"preview_id": "preview", "name": "cases", "idempotency_key": "submit", "token": "x"}
        )
