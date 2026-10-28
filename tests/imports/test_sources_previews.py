"""Pinned source, raw-JSON, and real sandbox preview regression tests."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from llm_evaluation_hub.core.datasets.catalog import DatasetRepository, ImportStore
from llm_evaluation_hub.imports.contracts import PreviewRequest, SampleRequest, SourceSpec
from llm_evaluation_hub.imports.jobs import ImportSupervisor
from llm_evaluation_hub.imports.previews import PreviewService, SampleLookupError, execute_preview
from llm_evaluation_hub.imports.runtime import ProcessorError
from llm_evaluation_hub.imports.sources import HuggingFaceAdapter, collect_sample

CODE = """def process(row):
    return {"conversation": [{"role": "user", "content": row["text"]}],
            "expected_output": row.get("nested"), "tools": row.get("tools", [])}
"""


class SyntheticSource:
    def resolve(self, source: SourceSpec) -> str:
        return "a" * 40

    def rows(
        self, source: SourceSpec, resolved_sha: str, limit: int
    ) -> Iterator[dict[str, object]]:
        assert resolved_sha == "a" * 40
        for index in range(limit):
            yield {"text": f"hi {index}", "nested": {"v": [index, None]}}


class LocalOperations:
    """Run the identical child callables for focused cache/persistence tests."""

    def run_operation(
        self, kind: Literal["sample", "preview"], payload: dict[str, object], *, timeout: float = 30
    ) -> dict[str, object]:
        if kind == "sample":
            request = SampleRequest.model_validate(payload)
            return collect_sample(SyntheticSource(), request.source, request.row_limit)
        raise AssertionError("Unexpected preview operation")


def test_sample_preserves_nested_json_and_order() -> None:
    result = collect_sample(SyntheticSource(), SourceSpec(repo_id="org/data"), 2)
    assert result == {
        "resolved_sha": "a" * 40,
        "rows": [
            {"text": "hi 0", "nested": {"v": [0, None]}},
            {"text": "hi 1", "nested": {"v": [1, None]}},
        ],
        "columns": [{"name": "nested", "types": ["dict"]}, {"name": "text", "types": ["str"]}],
    }
    rows = collect_sample(SyntheticSource(), SourceSpec(repo_id="org/data"), 100)["rows"]
    assert isinstance(rows, list) and len(rows) == 10


@pytest.mark.parametrize("repo", ["csv", "json", "parquet", "text", "arrow", "imagefolder"])
def test_builtin_loader_names_never_reach_hub_or_loader(repo: str) -> None:
    adapter = HuggingFaceAdapter()
    source = SourceSpec(repo_id=repo)
    with pytest.raises(ProcessorError, match="repository ID"):
        adapter.resolve(source)
    with pytest.raises(ProcessorError, match="repository ID"):
        next(adapter.rows(source, "a" * 40, 1))


@pytest.mark.parametrize(
    "repo", ["/tmp/data", "./local", "../local", "https://host/data", r"C:\data"]
)
def test_paths_and_urls_rejected(repo: str) -> None:
    with pytest.raises((ValidationError, ValueError)):
        SourceSpec(repo_id=repo)


def test_hf_adapter_pins_sha_and_uses_only_owned_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def loader(path: str, **kwargs: object) -> Iterator[dict[str, object]]:
        calls.append({"path": path, **kwargs})
        yield {"x": {"nested": [1, None]}}
        raise AssertionError("Read past requested prefix")

    monkeypatch.setattr("llm_evaluation_hub.imports.sources.load_dataset", loader)
    source = SourceSpec(repo_id="org/data", config="nested", split="test")
    rows = list(HuggingFaceAdapter().rows(source, "b" * 40, 1))
    assert rows == [{"x": {"nested": [1, None]}}]
    assert calls == [
        {
            "path": "hf://datasets/org/data",
            "name": "nested",
            "split": "test",
            "revision": "b" * 40,
            "streaming": True,
        }
    ]


def test_source_failure_does_not_expose_provider_details(monkeypatch: pytest.MonkeyPatch) -> None:
    def loader(*args: object, **kwargs: object) -> None:
        raise RuntimeError("secret credential /home/private/path")

    monkeypatch.setattr("llm_evaluation_hub.imports.sources.load_dataset", loader)
    with pytest.raises(ProcessorError) as raised:
        list(HuggingFaceAdapter().rows(SourceSpec(repo_id="org/data"), "a" * 40, 1))
    assert "secret" not in raised.value.message
    assert "/home" not in raised.value.message


@pytest.mark.parametrize("value", [float("nan"), {1, 2}, b"binary"])
def test_source_rejects_non_json_values(value: object) -> None:
    class InvalidSource(SyntheticSource):
        def rows(
            self, source: SourceSpec, resolved_sha: str, limit: int
        ) -> Iterator[dict[str, object]]:
            yield {"invalid": value}

    with pytest.raises(ProcessorError):
        collect_sample(InvalidSource(), SourceSpec(repo_id="org/data"), 1)


def test_preview_uses_real_monty_and_accepts_all_skipped() -> None:
    result = execute_preview([{"text": "x"}], "def process(row):\n    return None", [])
    assert result["valid"] and result["rows_dropped"] == 1
    assert result["rows"] == [
        {"source_index": 0, "status": "skipped", "example": None, "error": None}
    ]


def test_preview_reports_safe_row_and_segment_failures() -> None:
    result = execute_preview([{"text": "good"}, {"text": 12345}], CODE, [])
    assert not result["valid"] and result["rows_kept"] == 1
    assert "12345" not in str(result)
    result = execute_preview([{"text": "ok"}], CODE, ["language"])
    assert not result["valid"]
    assert "segments" in str(result)


def test_sample_cache_distinguishes_expiry_and_evicts_oldest(tmp_path: Path) -> None:
    service = PreviewService(ImportStore(tmp_path), LocalOperations())
    request = SampleRequest(source=SourceSpec(repo_id="org/data"))
    first = service.sample(request)
    first.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(SampleLookupError) as expired:
        service.preview(PreviewRequest(sample_id=first.id, source_code=CODE))
    assert expired.value.expired
    for _ in range(10):
        service.sample(request)
    with pytest.raises(SampleLookupError) as missing:
        service.preview(PreviewRequest(sample_id=first.id, source_code=CODE))
    assert not missing.value.expired
    assert len(service.samples) == 10


def test_service_real_worker_attests_only_valid_previews_without_publication(
    tmp_path: Path,
) -> None:
    supervisor = ImportSupervisor(tmp_path, source_adapter=SyntheticSource())
    service = PreviewService(supervisor.store, supervisor)
    sample = service.sample(SampleRequest(source=SourceSpec(repo_id="org/data"), row_limit=2))
    preview = service.preview(PreviewRequest(sample_id=sample.id, source_code=CODE))
    assert preview.valid and preview.id and preview.rows_kept == 2
    attestation = supervisor.store.get_preview(preview.id)
    assert attestation is not None
    spec = attestation["spec"]
    assert isinstance(spec, dict) and "rows" not in spec
    failed = service.preview(
        PreviewRequest(sample_id=sample.id, source_code=CODE, segment_keys=["x"])
    )
    assert not failed.valid and failed.id is None
    assert DatasetRepository(tmp_path).list_datasets() == []


def test_hf_resolution_uses_requested_revision_and_sanitizes_auth_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from huggingface_hub import HfApi

    calls: list[tuple[str, str]] = []

    def info(self: HfApi, repo_id: str, *, revision: str) -> SimpleNamespace:
        calls.append((repo_id, revision))
        return SimpleNamespace(sha="c" * 40)

    monkeypatch.setattr(HfApi, "dataset_info", info)
    assert HuggingFaceAdapter().resolve(SourceSpec(repo_id="org/data", revision="v2")) == "c" * 40
    assert calls == [("org/data", "v2")]

    def denied(self: HfApi, repo_id: str, *, revision: str) -> None:
        raise RuntimeError("Bearer private-auth-token")

    monkeypatch.setattr(HfApi, "dataset_info", denied)
    with pytest.raises(ProcessorError) as raised:
        HuggingFaceAdapter().resolve(SourceSpec(repo_id="org/data"))
    assert "private-auth-token" not in raised.value.message


def test_sample_rejects_oversized_source_row() -> None:
    class OversizedSource(SyntheticSource):
        def rows(
            self, source: SourceSpec, resolved_sha: str, limit: int
        ) -> Iterator[dict[str, object]]:
            yield {"text": "x" * 1048576}

    with pytest.raises(ProcessorError, match="1 MiB"):
        collect_sample(OversizedSource(), SourceSpec(repo_id="org/data"), 1)


def test_hub_loader_cannot_select_same_named_local_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from datasets.load import dataset_module_factory

    (tmp_path / "org" / "data").mkdir(parents=True)
    (tmp_path / "org" / "data" / "private.jsonl").write_text('{"secret": "local"}\n')
    monkeypatch.chdir(tmp_path)

    def local_forbidden(self: object) -> None:
        raise AssertionError("Hub import dispatched to local file loader")

    def remote_seen(self: object, *args: object, **kwargs: object) -> None:
        raise RuntimeError("remote dispatch confirmed")

    monkeypatch.setattr("datasets.load.LocalDatasetModuleFactory.get_module", local_forbidden)
    monkeypatch.setattr("datasets.load.HfApi.hf_hub_download", remote_seen)
    monkeypatch.setattr("datasets.load.CachedDatasetModuleFactory.get_module", remote_seen)
    with pytest.raises(RuntimeError, match="remote dispatch confirmed"):
        dataset_module_factory("hf://datasets/org/data", revision="a" * 40)
