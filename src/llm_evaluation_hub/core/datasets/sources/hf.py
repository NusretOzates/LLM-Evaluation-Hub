"""Hugging Face dataset source."""

import os

import polars as pl
from huggingface_hub import HfApi

from datasets import load_dataset
from llm_evaluation_hub.datasets.sources.protocol import SourceDescriptor


class HfDatasetSource:
    """Load one Hub dataset split and expose it as a Polars frame.

    The token is read from the constructor or `HF_TOKEN`. It is not part of
    `describe()` and is not written by the catalog.
    """

    def __init__(
        self,
        repo_id: str,
        split: str,
        *,
        config: str | None = None,
        revision: str | None = None,
        token: str | None = None,
    ) -> None:
        """Store Hub coordinates. The commit SHA is resolved on read."""
        if repo_id == "" or split == "":
            raise ValueError("repo_id and split must not be empty")
        self.repo_id = repo_id
        self.split = split
        self.config = config
        self.revision = revision
        self._token = token
        self._resolved_sha: str | None = None

    def read(self, *, limit: int | None = None) -> pl.DataFrame:
        """Resolve the commit SHA, then load that revision as a Polars frame."""
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        split = self._split_argument(limit)
        token = self._resolve_token()
        sha = HfApi().dataset_info(self.repo_id, revision=self.revision, token=token).sha
        self._resolved_sha = sha
        dataset = load_dataset(
            self.repo_id,
            name=self.config,
            split=split,
            revision=sha,
            token=token,
        )
        frame = dataset.to_polars()
        if not isinstance(frame, pl.DataFrame):
            raise TypeError("Hugging Face dataset did not convert to a Polars frame")
        return frame

    def describe(self) -> SourceDescriptor:
        """Return Hub coordinates and the SHA resolved by the last read."""
        return SourceDescriptor(
            source_type="hf_dataset",
            repo_id=self.repo_id,
            config=self.config,
            split=self.split,
            revision=self.revision,
            resolved_sha=self._resolved_sha,
        )

    def _split_argument(self, limit: int | None) -> str:
        """Return the Hub split, using a prefix slice only for a plain split name."""
        if limit is None:
            return self.split
        if "[" in self.split:
            raise ValueError("use a plain split name with limit")
        return f"{self.split}[:{limit}]"

    def _resolve_token(self) -> str | None:
        """Use the constructor token when it is set, otherwise `HF_TOKEN`."""
        if self._token is not None:
            return self._token
        return os.environ.get("HF_TOKEN")
