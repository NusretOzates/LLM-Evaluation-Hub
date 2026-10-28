"""Trusted streaming source adapters with bounded plain-JSON sampling."""

from collections.abc import Iterator
from itertools import islice
from typing import Protocol

from datasets.packaged_modules import _PACKAGED_DATASETS_MODULES
from huggingface_hub import HfApi
from huggingface_hub.utils import validate_repo_id

from datasets import load_dataset
from llm_evaluation_hub.imports.contracts import SAMPLE_ROWS, SourceSpec
from llm_evaluation_hub.imports.runtime import ProcessorError, validate_json_budget


def _hub_source(source: SourceSpec) -> None:
    """Exclude local loaders before datasets can interpret a repository name."""
    try:
        validate_repo_id(source.repo_id)
        if source.repo_id in _PACKAGED_DATASETS_MODULES or source.repo_id.startswith("."):
            raise ValueError
    except ValueError as error:
        raise ProcessorError("source", "Use a Hugging Face dataset repository ID.") from error


class SourceAdapter(Protocol):
    """Trusted constructor-injected source operations; never supplied over HTTP."""

    def resolve(self, source: SourceSpec) -> str:
        """Resolve a source revision to its immutable commit."""
        ...

    def rows(
        self, source: SourceSpec, resolved_sha: str, limit: int
    ) -> Iterator[dict[str, object]]:
        """Yield the ordered prefix from the resolved source."""
        ...


class HuggingFaceAdapter:
    """Resolve real Hub repositories and stream the same pinned revision."""

    def resolve(self, source: SourceSpec) -> str:
        """Resolve a dataset on the Hub without exposing provider diagnostics."""
        _hub_source(source)
        try:
            sha = HfApi().dataset_info(source.repo_id, revision=source.revision).sha
            if not sha:
                raise ValueError
            return sha
        except Exception as error:
            raise ProcessorError(
                "source", "Unable to resolve the Hugging Face dataset revision."
            ) from error

    def rows(
        self, source: SourceSpec, resolved_sha: str, limit: int
    ) -> Iterator[dict[str, object]]:
        """Read a bounded prefix using only server-owned loader arguments."""
        _hub_source(source)
        try:
            stream = load_dataset(
                f"hf://datasets/{source.repo_id}",
                name=source.config,
                split=source.split,
                revision=resolved_sha,
                streaming=True,
            )
            for item in islice(stream, limit):
                row = dict(item)
                validate_json_budget(row, category="source")
                yield row
        except ProcessorError:
            raise
        except Exception as error:
            raise ProcessorError(
                "source", "Unable to stream rows from the pinned dataset revision."
            ) from error


def collect_sample(adapter: SourceAdapter, source: SourceSpec, row_limit: int) -> dict[str, object]:
    """Collect at most ten ordered JSON rows with a ten-MiB aggregate budget."""
    sha = adapter.resolve(source)
    rows: list[dict[str, object]] = []
    size = 0
    for row in islice(
        adapter.rows(source, sha, min(row_limit, SAMPLE_ROWS)), min(row_limit, SAMPLE_ROWS)
    ):
        size += validate_json_budget(row, category="source")
        if size > 10 * 1048576:
            raise ProcessorError("resource_limit", "Source sample exceeds its 10 MiB limit.")
        rows.append(row)
    types: dict[str, set[str]] = {}
    for row in rows:
        for key, value in row.items():
            types.setdefault(key, set()).add("null" if value is None else type(value).__name__)
    return {
        "resolved_sha": sha,
        "rows": rows,
        "columns": [{"name": k, "types": sorted(v)} for k, v in sorted(types.items())],
    }
