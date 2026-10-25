"""In-memory dataset source for catalog tests."""

import polars as pl

from llm_evaluation_hub.datasets.sources.protocol import SourceDescriptor


class MemorySource:
    """A frame that already lives in memory."""

    def __init__(self, frame: pl.DataFrame) -> None:
        """Store the frame returned by read."""
        self.frame = frame
        self.limit_seen: int | None = None

    def read(self, *, limit: int | None = None) -> pl.DataFrame:
        """Return the frame, or its prefix when limit is set."""
        self.limit_seen = limit
        if limit is None:
            return self.frame
        return self.frame.head(limit)

    def describe(self) -> SourceDescriptor:
        """Return a descriptor with no Hub coordinates and no secrets."""
        return SourceDescriptor(source_type="memory")
