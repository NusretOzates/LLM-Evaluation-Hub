"""Dataset source contract. Implementations live beside this protocol."""

from typing import Protocol

import polars as pl
from pydantic import BaseModel, ConfigDict


class SourceDescriptor(BaseModel):
    """Provenance for one read. Secrets such as tokens are not fields."""

    model_config = ConfigDict(extra="forbid")

    source_type: str
    repo_id: str | None = None
    config: str | None = None
    split: str | None = None
    revision: str | None = None
    resolved_sha: str | None = None


class DatasetSource(Protocol):
    """A tabular source that can describe itself without reading row contents."""

    def read(self, *, limit: int | None = None) -> pl.DataFrame:
        """Return the source table, optionally limited to a prefix."""
        ...

    def describe(self) -> SourceDescriptor:
        """Return provenance for the latest read."""
        ...
